# Missing Evidence Can Still Reach Complete

## What the replay demonstrates

A real Alpha1 native-adapter run completed even though the only evidence named by its task did not exist. The worker Finding Pack pointed to `evidence/missing-experiment.json`; the isolated replay confirmed that this path was absent. A coordinator then passed the same text to the review command as a checked anchor. Alpha1 accepted the string without opening or resolving an artifact, marked the task completed and verified, and allowed the run to become complete.

This is separate from forged validation. The Finding Pack does not claim that a validation oracle passed and contains no `validation_result`. The failure is in the review lifecycle: saying that an anchor was checked is treated as evidence that it was checked.

## Operational meaning

A user reading Alpha1's final status could believe that the underlying experiment existed and had been reviewed. The durable state proves only that a matching anchor string was supplied. The receipt is therefore classified as a vulnerability reproduction, not as fix confirmation. A future candidate evaluation must require the reviewed evidence reference to resolve to a governed artifact and must record independently reviewable execution evidence.
