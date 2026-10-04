declare module "@mkkellogg/gaussian-splats-3d" {
  export class Viewer {
    constructor(options: Record<string, unknown>);
    addSplatScene(
      url: string,
      options?: Record<string, unknown>,
    ): Promise<void>;
    getSplatMesh(): { geometry: { instanceCount: number } };
    update(): void;
    render(): void;
    dispose(): Promise<void>;
  }
}
