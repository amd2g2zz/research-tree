## ADDED Requirements

### Requirement: provider discovery searches manifests, not usage bodies

`searchProviders` filters by capability, kind, or free-text keyword over
name/description/kinds; results are manifest lines only.

#### Scenario: kind search
- **WHEN** searching with kind "web-rendered"
- **THEN** only the agent-browser manifest is returned

#### Scenario: capability search
- **WHEN** searching with capability "search"
- **THEN** only search-capable manifests are returned

#### Scenario: usage bodies never ride search results
- **WHEN** any search returns
- **THEN** the serialized results contain no usage-guide text

### Requirement: usage loads only for selected providers, cached

`select(name)` gates `loadUsage`; loading is cached by name so a provider
costs exactly one context entry.

#### Scenario: unselected load is refused
- **WHEN** `loadUsage` is called for a provider that was never selected
- **THEN** it raises a registry error naming the provider

#### Scenario: repeated loads return the cached usage
- **WHEN** the same provider's usage is loaded twice
- **THEN** both calls return the identical string and the loaded count stays 1

#### Scenario: loaded never exceeds selected
- **WHEN** providers are selected and loaded in any order
- **THEN** `loadedUsageCount() <= selected().length` holds
