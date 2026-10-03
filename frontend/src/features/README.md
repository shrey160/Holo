# Frontend features

| Feature         | User task                                                         | Guide                                            |
| --------------- | ----------------------------------------------------------------- | ------------------------------------------------ |
| `guide`         | Prepare the phone/space and follow the room capture sequence      | [Guide feature](guide/README.md)                 |
| `ingestion`     | Upload an export, follow validation and download verified results | [Ingestion feature](ingestion/README.md)         |
| `preprocessing` | Review selected views, visual connections and motion findings     | [Preprocessing feature](preprocessing/README.md) |

[App.tsx](../App.tsx) composes the guide and input tabs and retains their state across tab switches. The ingestion result starts independent preprocessing jobs and embeds the preprocessing feature when their results are available. Each feature owns its screen behavior; [api/](../api/README.md) owns network transport and [components/](../components/README.md) owns shared presentation. Reconstruction remains a future stage with its own output contract.
