/* GNU timeout timer driver for logical-deadline-v1. No clock/time interposition.
 * All parsing, exit statuses, process groups, signals and --kill-after handling
 * remain in the installed GNU timeout binary. Other executables pass through.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;
static unsigned long generation;
static int active;
static char directory[512];
static int (*native_settime)(timer_t, int, const struct itimerspec *, struct itimerspec *);
static int (*native_delete)(timer_t);
static unsigned int (*native_alarm)(unsigned int);
static char lease[64];
static double target;

static void control_failed(const char *operation) {
    int saved = errno;
    dprintf(STDERR_FILENO, "benchmark GNU deadline control failed: %s (errno=%d)\n", operation, saved);
    /* Best-effort structured adapter fault, distinct from native exit 124.
     * Do not call rpc() here: a reporting failure must never recurse. */
    if (*directory) {
        int fd = socket(AF_UNIX, SOCK_STREAM, 0);
        struct sockaddr_un addr = {.sun_family = AF_UNIX};
        struct timeval limit = {.tv_usec = 200000};
        if (fd >= 0) {
            setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &limit, sizeof limit);
            setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &limit, sizeof limit);
            if (snprintf(addr.sun_path, sizeof addr.sun_path, "%s/broker.sock", directory) < (int)sizeof addr.sun_path &&
                !connect(fd, (void *)&addr, sizeof addr)) {
                const char notice[] = "{\"op\":\"failure\"}\n";
                if (send(fd, notice, sizeof notice - 1, MSG_NOSIGNAL) > 0) {
                    char reply[128];
                    (void)read(fd, reply, sizeof reply);
                }
            }
            close(fd);
        }
    }
    _exit(125);
}

static double physical_now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}

static double logical_now(void) {
    char path[600], buf[1024];
    snprintf(path, sizeof path, "%s/clock.json", directory);
    int fd;
    do { fd = open(path, O_RDONLY); } while (fd < 0 && errno == EINTR);
    if (fd < 0) control_failed("open clock");
    ssize_t n;
    do { n = read(fd, buf, sizeof buf - 1); } while (n < 0 && errno == EINTR);
    close(fd);
    if (n <= 0) control_failed("read clock");
    buf[n] = 0;
    char *l = strstr(buf, "\"logical\":"), *a = strstr(buf, "\"anchor\":");
    char *p = strstr(buf, "\"paused\":");
    if (!l || !a || !p) control_failed("parse clock");
    double value = strtod(strchr(l, ':') + 1, NULL);
    double anchor = strtod(strchr(a, ':') + 1, NULL);
    p = strchr(p, ':') + 1;
    while (*p == ' ') ++p;
    return value + (*p == 't' ? 0 : fmax(0, physical_now() - anchor));
}

static void rpc(const char *request, char *reply, size_t size) {
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    struct sockaddr_un addr = {.sun_family = AF_UNIX};
    if (snprintf(addr.sun_path, sizeof addr.sun_path, "%s/broker.sock", directory)
            >= (int)sizeof addr.sun_path) control_failed("socket path");
    struct timeval limit = {.tv_sec = 3};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &limit, sizeof limit);
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &limit, sizeof limit);
    if (fd < 0) control_failed("socket");
    int connected;
    do { connected = connect(fd, (void *)&addr, sizeof addr); } while (connected && errno == EINTR);
    if (connected && errno != EISCONN) control_failed("connect");
    size_t sent = 0, request_size = strlen(request);
    while (sent < request_size) {
        ssize_t n = send(fd, request + sent, request_size - sent, MSG_NOSIGNAL);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) control_failed("send");
        sent += n;
    }
    size_t pos = 0;
    while (pos + 1 < size) {
        ssize_t n = read(fd, reply + pos, size - pos - 1);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) break;
        pos += n;
        if (memchr(reply, '\n', pos)) break;
    }
    close(fd);
    reply[pos] = 0;
    if (!pos || strstr(reply, "\"error\"")) control_failed("receive or rejected RPC");
}

static void close_lease(void) {
    if (*lease) {
        char req[128], reply[256];
        snprintf(req, sizeof req, "{\"op\":\"close\",\"id\":\"%s\"}\n", lease);
        rpc(req, reply, sizeof reply);
        *lease = 0;
    }
}

struct watch { unsigned long generation; timer_t timer; int alarm; };

static void *watch(void *data) {
    /* Only GNU timeout's main thread should execute its signal handler;
     * that handler may rearm --kill-after and take mu again. */
    sigset_t blocked;
    sigemptyset(&blocked);
    sigaddset(&blocked, SIGALRM);
    pthread_sigmask(SIG_BLOCK, &blocked, NULL);
    struct watch job = *(struct watch *)data;
    free(data);
    for (;;) {
        pthread_mutex_lock(&mu);
        if (generation != job.generation) {
            pthread_mutex_unlock(&mu);
            return NULL;
        }
        if (logical_now() >= target) {
            /* Keep the lease until native timeout exits or rearms kill-after.
             * The host's delivery barrier must not race the native handler. */
            if (job.alarm) kill(getpid(), SIGALRM);
            else {
                struct itimerspec immediate = {.it_value = {.tv_nsec = 1}};
                native_settime(job.timer, 0, &immediate, NULL);
            }
            pthread_mutex_unlock(&mu);
            return NULL;
        }
        pthread_mutex_unlock(&mu);
        struct timespec tick = {.tv_nsec = 20000000};
        nanosleep(&tick, NULL);
    }
}

static void arm(timer_t timer, double seconds, int alarm) {
    pthread_mutex_lock(&mu);
    ++generation;
    close_lease();
    if (seconds > 0) {
        char req[128], reply[512];
        snprintf(req, sizeof req, "{\"op\":\"register\",\"seconds\":%.9f}\n", seconds);
        rpc(req, reply, sizeof reply);
        char *id = strstr(reply, "\"id\":");
        char *end = strstr(reply, "\"target\":");
        if (!id || !end) control_failed("parse lease");
        id = strchr(id, ':') + 1;
        while (*id == ' ') ++id;
        if (*id++ != '"' || strlen(id) < 33 || id[32] != '"') control_failed("parse lease id");
        memcpy(lease, id, 32); lease[32] = 0;
        target = strtod(strchr(end, ':') + 1, NULL);
        struct watch *job = malloc(sizeof *job);
        if (!job) control_failed("allocate watcher");
        *job = (struct watch){generation, timer, alarm};
        pthread_t thread;
        if (pthread_create(&thread, NULL, watch, job)) control_failed("start watcher");
        pthread_detach(thread);
    }
    pthread_mutex_unlock(&mu);
}

__attribute__((constructor)) static void init(void) {
    native_settime = dlsym(RTLD_NEXT, "timer_settime");
    native_delete = dlsym(RTLD_NEXT, "timer_delete");
    native_alarm = dlsym(RTLD_NEXT, "alarm");
    const char *dir = getenv("BENCHMARK_DEADLINE_DIR");
    char exe[1024]; ssize_t n = readlink("/proc/self/exe", exe, sizeof exe - 1);
    if (!dir || n < 0) return;
    exe[n] = 0;
    char *base = strrchr(exe, '/');
    active = base && !strcmp(base + 1, "timeout");
    if (active) {
        if (strlen(dir) >= sizeof directory) control_failed("directory path");
        strcpy(directory, dir);
    }
}

int timer_settime(timer_t timer, int flags, const struct itimerspec *value,
                  struct itimerspec *old) {
    if (!active || flags || value->it_interval.tv_sec || value->it_interval.tv_nsec)
        return native_settime(timer, flags, value, old);
    struct itimerspec off = {0};
    int result = native_settime(timer, 0, &off, old);
    if (!result) arm(timer, value->it_value.tv_sec + value->it_value.tv_nsec / 1e9, 0);
    return result;
}

int timer_delete(timer_t timer) {
    if (active) arm(timer, 0, 0);
    return native_delete(timer);
}

unsigned int alarm(unsigned int seconds) {
    if (!active) return native_alarm(seconds);
    unsigned int previous = native_alarm(0);
    arm((timer_t)0, seconds, 1);
    return previous;
}
