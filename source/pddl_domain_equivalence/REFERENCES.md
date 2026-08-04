# References and implementation provenance

## Primary planning-domain reference

Lukáš Chrpa, Carmine Dodaro, Marco Maratea, Marco Mochi, and Mauro Vallati.
"Comparing Planning Domain Models using Answer Set Programming." In *Logics in
Artificial Intelligence (JELIA 2023)*, 2023.

- Paper:
  <https://pure.hud.ac.uk/files/67535650/JELIA_2023_Similarity_and_ASP.pdf>
- Authors' experiment repository:
  <https://github.com/MarcoMochi/jelia-planning>

Reused ideas:

- strong equivalence as a global bijection over predicate/operator structure;
- a lifted domain model graph connecting operators to preconditions, delete effects,
  and add effects;
- encoding parameter bindings so that renaming does not erase argument roles;
- reducing strong domain equivalence to labelled graph isomorphism.

This package does not copy the authors' ASP encoding or source code. It constructs a
different expanded directed graph and delegates exact graph isomorphism to NetworkX.
The graph is extended with explicit PDDL type hierarchy, predicate/action signature
positions, domain constants, negative-precondition roles, literal occurrences, and
argument-binding nodes.

The JELIA graph-edit-distance/ASP similarity optimizer is not implemented here.

## Earlier definition of planning-domain equivalence

Muhammad Shoeeb and Thomas L. McCluskey. "On Comparing Planning Domain Models."
In the ICAPS 2011 Workshop on Knowledge Engineering for Planning and Scheduling,
2011.

- Paper: <https://eprints.hud.ac.uk/id/eprint/12717/1/PlanSig_paper_1.pdf>

This work is cited for the earlier distinction between strong structural equivalence
and weaker behavioural notions.

## Graph-isomorphism implementation

NetworkX Developers. "Isomorphism — NetworkX documentation."

- Documentation:
  <https://networkx.org/documentation/stable/reference/algorithms/isomorphism.html>

The checker uses `networkx.algorithms.isomorphism.DiGraphMatcher` with categorical
node and edge attributes. NetworkX's matcher implements the VF2 family of practical
graph-isomorphism algorithms.

Luigi P. Cordella, Pasquale Foggia, Carlo Sansone, and Mario Vento. "A
(Sub)Graph Isomorphism Algorithm for Matching Large Graphs." *IEEE Transactions on
Pattern Analysis and Machine Intelligence* 26(10), 2004.

- DOI: <https://doi.org/10.1109/TPAMI.2004.75>

