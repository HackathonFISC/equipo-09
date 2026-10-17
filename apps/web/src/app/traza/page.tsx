import type { Metadata } from "next";

import { PageShell, RoleHeader } from "@/components/page-shell";
import { TraceList } from "@/components/trace-list";

export const metadata: Metadata = { title: "Corridas recientes" };

export default function TrazaIndexPage() {
	return (
		<PageShell width="narrow">
			<RoleHeader
				title="Corridas recientes"
				description="Cada vez que los agentes trabajan, queda un recorrido: quién decidió qué, con qué herramienta y por qué. Abre uno para ver la explicación paso a paso."
			/>
			<TraceList />
		</PageShell>
	);
}
