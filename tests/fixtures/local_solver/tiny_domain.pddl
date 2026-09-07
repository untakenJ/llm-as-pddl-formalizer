(define (domain local-solver-smoke)
  (:requirements :strips)
  (:predicates (at-a) (at-b))
  (:action go
    :parameters ()
    :precondition (at-a)
    :effect (and (not (at-a)) (at-b))))
