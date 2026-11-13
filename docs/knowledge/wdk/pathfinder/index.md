# WDK and Strategist

Where Strategist corresponds to WDK, what Strategist owns outright, and where it diverges
deliberately. These explain; they do not assert. Assertions live in the rules (`veupathdb-py: docs/knowledge/wdk/rules/`).

- [Which repository wins, and which sites this application is verified on](sources-and-authority.md) - the authority ranking, the two verification sites, and the one live test that looks like evidence and is not
- [What corresponds to what](type-correspondence.md) - the four-column map from WDK Java to `wdk-client` to Pydantic to `@strategist/shared`, the two splits Strategist makes that upstream does not, and every empty cell labelled
- [Who is allowed to talk to WDK](layer-ownership.md) - the import-linter contracts, what each actually forbids, the WDK service functions that replaced the re-export seam, and the two things no contract can see
- [Where Strategist deliberately differs from WDK](deliberate-divergences.md) - nine divergences with the decision that records what was rejected, and the test that keeps a bug from being filed as one
