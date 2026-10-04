# Frontend features

| Feature          | User task                                                               | Guide                                              |
| ---------------- | ----------------------------------------------------------------------- | -------------------------------------------------- |
| `guide`          | Prepare the phone/space and follow the room capture sequence            | [Guide feature](guide/README.md)                   |
| `ingestion`      | Upload an export, follow validation and download verified results       | [Ingestion feature](ingestion/README.md)           |
| `preprocessing`  | Review selected views, visual connections and motion findings           | [Preprocessing feature](preprocessing/README.md)   |
| `reconstruction` | Inspect published rough plans, RGB point clouds and structural evidence | [Reconstruction feature](reconstruction/README.md) |

[App.tsx](../App.tsx) composes the guide, input and reconstruction tabs. It retains input state across switches and lazily mounts/disposes the reconstruction feature. The ingestion result starts independent preprocessing jobs and embeds their review. Each feature owns its screen behavior; [api/](../api/README.md) owns ingestion transport, reconstruction `types.ts` owns its abortable asset helper and [components/](../components/README.md) owns shared presentation. Reconstruction displays separately published audited outputs; automatic reconstruction from new uploads remains subsequent work.
