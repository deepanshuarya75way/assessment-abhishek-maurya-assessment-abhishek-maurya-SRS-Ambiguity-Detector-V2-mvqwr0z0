"""Optional AI enhancement: provider ABC + registry + adapters. Fail-open by contract.

Stage 12 landed the abstraction (`providers.AIProvider`), the metadata registry,
and the Fernet vault (`app.core.vault`). Stages 14 and 18 completed the six
provider adapters (`adapters/`), versioned prompts (`prompts/`), the sanitizer,
and the model table — no provider-specific code may live outside this package +
the registry table (AI_PROVIDER_SPEC §4).
"""
