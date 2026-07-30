# Security and collection ownership

## Plugin-owned collections

The default policy maps logical names to:

```text
endstone-plugin:<normalized-plugin-id>:<logical-name>
```

A normal plugin can only capture, list, or mutate collections under its prefix.

`AccessContext` is supplied by the hosting provider. It must be constructed from the authenticated plugin or command boundary; it is unsafe to let an untrusted caller choose `plugin_id` or assert `raw_admin`.

## Raw administration

Raw mode supports:

- behavior-pack UUID collection access;
- abandoned collection discovery;
- cross-plugin recovery;
- collection rename and migration;
- destructive collection removal;
- full export for backup.

The API requires `AccessContext.raw_admin=true`; the consuming Endstone plugin must grant that context only after checking a permission such as `endstone.dynamicproperties.admin`.

A plugin may clear or remove a collection within its own namespace. Raw administration is required to remove or migrate collections outside that namespace.

## Audit fields

Audits include target, collection, key/operation, origin, actor/plugin identity, status, transaction ID, reason, external flag, and rollback flag. Sensitive values should be redacted by the configured sink when necessary.

## Limits

`ValidationLimits` guards key/collection lengths, string sizes, property counts, import documents, and transaction operation counts. Final property-count validation and commit are serialized across services sharing an adapter. These protections apply at the service boundary; direct adapter calls bypass them. The native adapter must also apply Bedrock’s own validation while holding its platform transaction lease.
