import { createFromSource } from "fumadocs-core/search/server";
import { source } from "@/lib/source";

// El tokenizador por defecto («multilingual») ya funciona con español.
export const { GET } = createFromSource(source);
