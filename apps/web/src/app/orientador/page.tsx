import {
	Ban,
	ListOrdered,
	type LucideIcon,
	Scale,
	Waypoints,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { MatchRunButton } from "@/components/match-run-button";
import { PageShell, RoleHeader } from "@/components/page-shell";
import { ReviewInbox } from "@/components/review-inbox";

export const metadata: Metadata = { title: "Bandeja de revisión" };

const kinds: { label: string; icon: LucideIcon; trigger: string }[] = [
	{
		label: "Bloqueo de oferta",
		icon: Ban,
		trigger:
			"Mercado (reglas y LLM) encontró un requisito discriminatorio en una oferta.",
	},
	{
		label: "Lista corta",
		icon: ListOrdered,
		trigger:
			"Postulación propone candidatos para una vacante; usted aprueba, reordena o quita.",
	},
	{
		label: "Alerta de sesgo",
		icon: Scale,
		trigger:
			"Una prueba contrafactual (nombre, género o corregimiento) bajó la paridad.",
	},
];

export default function OrientadorPage() {
	return (
		<PageShell>
			<RoleHeader
				title="Bandeja de revisión"
				description="Las decisiones con impacto se detienen aquí hasta que usted las apruebe, edite o rechace. Cada una trae la propuesta del agente, su explicación y la traza."
				actions={
					<>
						<MatchRunButton />
						<Link
							href="/traza"
							className="inline-flex min-h-11 items-center gap-2 border px-4 font-medium text-sm outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50"
						>
							<Waypoints className="size-4" aria-hidden="true" />
							Corridas recientes
						</Link>
					</>
				}
			/>

			<ReviewInbox />

			<section aria-labelledby="tipos" className="flex flex-col gap-3">
				<h2 id="tipos" className="font-medium text-sm">
					Qué puede llegar a la bandeja
				</h2>
				<dl className="grid gap-x-8 gap-y-4 border-t pt-4 md:grid-cols-3">
					{kinds.map(({ label, icon: Icon, trigger }) => (
						<div key={label} className="flex gap-3">
							<Icon
								className="mt-0.5 size-5 shrink-0 text-warning-fg"
								aria-hidden="true"
							/>
							<div className="flex flex-col gap-0.5">
								<dt className="font-medium text-sm">{label}</dt>
								<dd className="text-muted-foreground text-sm">{trigger}</dd>
							</div>
						</div>
					))}
				</dl>
			</section>
		</PageShell>
	);
}
