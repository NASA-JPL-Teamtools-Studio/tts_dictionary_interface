# Implementation Spec: SemanticDictionary Node Caching
## Overview
This specification outlines the implementation of a caching mechanism for `SemanticDictionary` to resolve performance issues caused by repeated XML parsing and XPath lookups.
## Design Decisions
### 1. Cache Scope and Lifecycle
- **Scope**: Session-scoped. Each `SemanticDictionary` instance will maintain its own private cache.
- **Lifecycle**: The cache is created upon instantiation and lives for the duration of the object.
### 2. Cache Mechanism
- **Type**: A Python dictionary used as an LRU (Least Recently Used) cache.
- **Capacity**: Bounded to 100 entries to prevent unbounded memory growth.
- **Concurrency**: Non-thread-safe (to minimize overhead, per developer requirement).
### 3. Keying Strategy
To avoid collisions between different lookup methods, the cache will use a composite key: `(lookup_type, lookup_value)`.
| Method | `lookup_type` | `lookup_value` |
|---|---|---|
| `__getitem__` | `'getitem'` | The item ID (e.g., command stem) |
| `__contains__` | `'getitem'` | The key being checked |
| `__getattr__` | `'getattr'` | The attribute name |
| `__iter__` | `'getitem'` | The item ID (from `ITEM_HUMAN_UNIQUE_IDS`) |
### 4. Detailed Implementation Plan
#### A. Initialization
Add `self._cache = collections.OrderedDict()` to `SemanticDictionary.__init__`.
#### B. `__getitem__` and `__contains__`
- Check `self._cache.get(('getitem', item))`.
- If present, return/confirm.
- If absent:
    - Perform the existing XPath logic.
    - If a result is found, wrap it in the appropriate `ITEM_CLASS`.
    - Add to `self._cache` with key `('getitem', item)`.
    - Maintain LRU order by moving the key to the end if it exists, or removing the oldest if size > 100.
#### C. `__getattr__`
- Check `self._cache.get(('getattr', attr))`.
- If present, return.
- If absent:
    - Perform existing logic.
    - Store result in `self._cache` with key `('getattr', attr)`.
    - Maintain LRU order.
#### D. `__iter__` and `__len__`
- `__iter__` will implement "lazy population":
    - Iterate through `ITEM_XPATHS` and `ITEM_HUMAN_UNIQUE_IDS`.
    - For each item, perform the wrap and store in `self._cache` using `('getitem', identifier)`.
- `__len__` will return the count of items in the `'getitem'` cache after the first iteration has completed, or a cached count.
#### E. Invalidation
- No explicit `refresh()` method will be implemented at this time, as per developer request.
## Verification Plan
1. **Profiling**: Run `profile_test.py` to confirm the speedup factor (expected >10x for subsequent accesses).
2. **Correctness**: Ensure `__getitem__`, `__getattr__`, `__contains__`, and `__iter__` all return correct, consistent data.
