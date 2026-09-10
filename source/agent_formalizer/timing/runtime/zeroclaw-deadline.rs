//! Adapter-owned replacement for named shell and model-gateway deadlines.
//! Physical Instant/SystemTime, native output, signals and cleanup stay native.
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixStream;
use std::time::Duration;
type ControlError = Box<dyn std::error::Error + Send + Sync>;

struct Lease {
    directory: std::path::PathBuf,
    id: String,
    target: f64,
    physical_anchor: f64,
    local_anchor: std::time::Instant,
}

impl Lease {
    fn rpc(directory: &std::path::Path, request: serde_json::Value) -> Result<serde_json::Value, ControlError> {
        let mut socket = UnixStream::connect(directory.join("broker.sock"))?;
        socket.set_read_timeout(Some(Duration::from_secs(3)))?;
        socket.set_write_timeout(Some(Duration::from_secs(3)))?;
        writeln!(socket, "{}", request)?;
        let mut line = String::new();
        BufReader::new(socket).read_line(&mut line)?;
        let reply: serde_json::Value = serde_json::from_str(&line)?;
        if reply.get("error").is_some() { return Err("deadline control rejected".into()); }
        Ok(reply)
    }

    fn new(directory: std::path::PathBuf, seconds: f64) -> Result<Self, ControlError> {
        let result = Self::rpc(&directory, serde_json::json!({"op":"register", "seconds":seconds}))?;
        Ok(Self {
            directory,
            id: result["id"].as_str().ok_or("missing deadline id")?.to_owned(),
            target: result["target"].as_f64().ok_or("missing deadline target")?,
            physical_anchor: result["physical_monotonic"].as_f64().ok_or("missing monotonic anchor")?,
            local_anchor: std::time::Instant::now(),
        })
    }

    fn expired(&self) -> Result<bool, ControlError> {
        let state: serde_json::Value = serde_json::from_slice(&std::fs::read(self.directory.join("clock.json"))?)?;
        let logical = state["logical"].as_f64().ok_or("missing logical time")?;
        let anchor = state["anchor"].as_f64().ok_or("missing physical anchor")?;
        let paused = state["paused"].as_bool().ok_or("missing deadline state")?;
        // Map stable Rust Instant to the host monotonic anchor from the one
        // registration exchange. Its sub-millisecond IPC skew is recorded by
        // boundary tests; no physical clock or native Instant is overridden.
        let now = self.physical_anchor + self.local_anchor.elapsed().as_secs_f64();
        Ok(logical + if paused { 0.0 } else { (now - anchor).max(0.0) } >= self.target)
    }
}

impl Drop for Lease {
    fn drop(&mut self) {
        let _ = Self::rpc(&self.directory, serde_json::json!({"op":"close", "id": self.id}));
    }
}

fn control_failure(error: ControlError) -> ! {
    if let Some(directory) = std::env::var_os("BENCHMARK_DEADLINE_DIR") {
        // Explicit adapter provenance; an ordinary native Elapsed/exit never
        // uses this path. The host records infrastructure invalidation.
        let _ = Lease::rpc(std::path::Path::new(&directory), serde_json::json!({"op":"failure"}));
    }
    eprintln!("benchmark native deadline control failed: {error}");
    std::process::exit(70)
}

pub async fn timeout<F: std::future::Future>(duration: Duration, future: F)
    -> Result<F::Output, tokio::time::error::Elapsed>
{
    let Some(directory) = std::env::var_os("BENCHMARK_DEADLINE_DIR") else {
        return tokio::time::timeout(duration, future).await;
    };
    let lease = Lease::new(directory.into(), duration.as_secs_f64()).unwrap_or_else(|e| control_failure(e));
    tokio::pin!(future);
    loop {
        // Tokio timeout polls its value before its delay. Preserve that order,
        // including the native rule for a value already ready at the deadline.
        tokio::select! {
            biased;
            result = &mut future => return Ok(result),
            _ = tokio::time::sleep(Duration::from_millis(20)) => {
                if lease.expired().unwrap_or_else(|e| control_failure(e)) {
                    return tokio::time::timeout(Duration::ZERO, std::future::pending()).await;
                }
            }
        }
    }
}
