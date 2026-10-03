# Frontend features

| Feature     | User task                                                         | Guide                                    |
| ----------- | ----------------------------------------------------------------- | ---------------------------------------- |
| `guide`     | Prepare the phone/space and follow the room capture sequence      | [Guide feature](guide/README.md)         |
| `ingestion` | Upload an export, follow validation and download verified results | [Ingestion feature](ingestion/README.md) |

[App.tsx](../App.tsx) composes the two features and retains their state across tab switches. Each feature owns its screen behavior; [api/](../api/README.md) owns network transport and [components/](../components/README.md) owns shared presentation. Future preprocessing/reconstruction screens should have their own contracts rather than being added to ingestion result semantics.
