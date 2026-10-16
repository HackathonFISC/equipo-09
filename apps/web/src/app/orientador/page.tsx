import {
	Ban,
	CircleCheck,
	ListOrdered,
	type LucideIcon,
	Scale,
} from "lucide-react";
import type { Metadata } from "next";

import { PageShell, RoleHeader } from "@/components/page-shell";

export const metadata: Metadata = { title: "Bandeja de revisión" };

const kinds: { label: string; icon: LucideIcon; trigger: string }[] = [
	{
		label: "Bloqueo de oferta",
		icon: Ban,
		trigger: "El Auditor encontró un requisito discriminatorio en una oferta.",
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

const columns = ["Tipo", "Agente", "Propuesta", "Antigüedad", "Impacto"];

export default function OrientadorPage() {
	return (
		<PageShell>
			<RoleHeader
				title="Bandeja de revisión"
				description="Las decisiones con impacto se detienen aquí hasta que usted las apruebe, edite o rechace. Cada una trae la propuesta del agente, su explicación y la traza."
			/>

			<section aria-labelledby="pendientes" className="flex flex-col gap-3">
				<h2 id="pendientes" className="font-medium text-sm">
					Pendientes
				</h2>
				<div className="overflow-x-auto border">
					<table className="w-full min-w-[40rem] text-sm">
						<thead className="bg-muted/60 text-left text-muted-foreground">
							<tr>
								{columns.map((c) => (
									<th key={c} scope="col" className="px-3 py-2 font-medium">
										{c}
									</th>
								))}
							</tr>
						</thead>
						<tbody>
							<tr>
								<td colSpan={columns.length} className="px-3 py-12">
									<div className="flex flex-col items-center gap-2 text-center">
										<CircleCheck
											className="size-6 text-success-fg"
											aria-hidden="true"
										/>
										<p className="font-medium">No hay decisiones pendientes</p>
										<p className="max-w-md text-muted-foreground">
											Cuando un agente necesite su visto bueno, la tarea
											aparecerá aquí y el flujo esperará su decisión.
										</p>
									</div>
								</td>
							</tr>
						</tbody>
					</table>
				</div>
			</section>

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
