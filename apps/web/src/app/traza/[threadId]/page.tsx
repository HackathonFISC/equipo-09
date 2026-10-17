import type { Metadata } from "next";

import { PageShell, RoleHeader } from "@/components/page-shell";
import { TraceView } from "@/components/trace-timeline";

export const metadata: Metadata = { title: "Traza de decisiones" };

export default async function TrazaPage({
	params,
}: {
	params: Promise<{ threadId: string }>;
}) {
	const { threadId } = await params;
	const id = decodeURIComponent(threadId);

	return (
		<PageShell width="narrow">
			<RoleHeader
				title="Cómo se decidió"
				description={
					<>
						Cada agente que participó, qué hizo, con qué herramienta y por qué.
						Cuando el flujo se detiene, la decisión es de una persona. Hilo:{" "}
						<span className="break-all font-mono text-sm">{id}</span>
					</>
				}
			/>
			<TraceView key={id} threadId={id} />
		</PageShell>
	);
}
