# datahub-yaml-source

A DataHub ingestion source that translates a tree of declarative YAML
("metadata as code") into the DataHub entities it describes, and emits them
to a DataHub server.

## Language

**Supported DataHub version**:
A version of the DataHub *server* (GMS) that this source is verified against
and guaranteed to work with. The announced range contains only verified
versions; an upcoming version joins it only after verification. The version
of the client library is not a commitment.
_Avoid_: DataHub version (ambiguous between server and client), acryl-datahub version

**Version check**:
The local, manual proof that a DataHub server minor keeps everything this
source emits: the test fixture is ingested into that server, and every emitted
aspect read back from it must still contain what was sent. Passing it is what
admits a minor into the range of **Supported DataHub versions**.
_Avoid_: Docker check, integration test, verification run

**Minimum server version**:
The oldest DataHub server minor that accepts a given entity type or aspect.
It equals the floor of the **Supported DataHub version** range unless a newer
kind or aspect declares a higher one. On an older supported server, what
needs a higher minimum is not emitted, and the run says so.
_Avoid_: per-kind floor, feature flag, version gate
