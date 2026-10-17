// Opciones globales de Fumadocs MDX. Las colecciones se declaran con la Macro API en lib/source.ts.
import { remarkMdxMermaid } from "fumadocs-core/mdx-plugins";
import { defineConfig } from "fumadocs-mdx/config";

export default defineConfig({
	mdxOptions: {
		// Los bloques ```mermaid se convierten en <Mermaid chart="..." />.
		remarkPlugins: [remarkMdxMermaid],
	},
});
