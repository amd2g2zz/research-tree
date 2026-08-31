## Why

`InteractionReducer` correctly removes dependent actions from semantic state when a correction supersedes their assumption, but `DurableInteractionController.submit` publishes the new semantic state without reconciling the separate persisted `pending_actions` map. A started dependent action can therefore remain durable and executable after its authority has been invalidated.

## What Changes

Derive the reducer transition before publishing a submitted event and remove only persisted action IDs that disappeared from semantic pending actions during that transition. Preserve every other action status in the same revisioned mutation, including tracked execution IDs that are not semantic action strings. Recovery from an older checkpoint must not resurrect an action invalidated by a later correction, and replaying the same correction event must not restore it.
