import { Button } from "@puente/ui/components/button";
import { MapPinned } from "lucide-react";
import type { Metadata } from "next";
import { connection } from "next/server";

import { PageShell, RoleHeader } from "@/components/page-shell";
import { loadLocations } from "@/lib/api/catalog";

export const metadata: Metadata = { title: "Mis oportunidades" };

const steps = [
	{
		title: "Cuéntanos cómo te mueves",
		detail:
			"Tu corregimiento, cuánto puedes gastar en pasaje al día, el tiempo máximo de viaje y tu horario.",
	},
	{
		title: "Arma tu perfil",
		detail:
			"Sube tu CV o una foto. Si no tienes, respondes máximo 8 preguntas y encontramos tus habilidades.",
	},
	{
		title: "Mira tus oportunidades",
		detail:
			"Solo ofertas a las que puedes llegar, con minutos de viaje, costo diario y por qué encajas.",
	},
];

export default async function JovenPage() {
	await connection();
	const locations = await loadLocations();
	const provinces = locations.ok
		? new Set(locations.data.map((l) => l.provincia))
		: null;

	return (
		<PageShell width="narrow">
			<RoleHeader
				title="Mis oportunidades"
				description="Aquí vas a ver las ofertas que te quedan cerca y te convienen. Primero necesitamos conocerte un poco."
			/>

			<section aria-labelledby="pasos" className="flex flex-col gap-6">
				<h2 id="pasos" className="font-medium text-lg">
					Aún no tienes perfil
				</h2>
				<ol className="flex flex-col gap-5">
					{steps.map((step, i) => (
						<li key={step.title} className="grid grid-cols-[2rem_1fr] gap-x-3">
							<span
								aria-hidden="true"
								className="tabular flex size-8 items-center justify-center border border-primary/40 font-mono text-primary text-sm"
							>
								{i + 1}
							</span>
							<span className="flex flex-col gap-0.5">
								<span className="font-medium">{step.title}</span>
								<span className="text-muted-foreground text-sm">
									{step.detail}
								</span>
							</span>
						</li>
					))}
				</ol>

				<div className="flex flex-col gap-2">
					<Button size="lg" className="h-12 w-full text-base" disabled>
						Empezar registro
					</Button>
					<p className="text-center text-muted-foreground text-sm">
						El registro se habilita en la próxima versión de esta demo.
					</p>
				</div>
			</section>

			{locations.ok && provinces ? (
				<p className="flex items-start gap-2 border-t pt-6 text-muted-foreground text-sm">
					<MapPinned className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
					<span>
						Hoy calculamos traslados desde{" "}
						<strong className="font-medium text-foreground">
							{locations.data.length} corregimientos
						</strong>{" "}
						de {[...provinces].join(" y ")}
						{locations.source === "mock" ? " (datos de ejemplo)" : ""}.
					</span>
				</p>
			) : null}
		</PageShell>
	);
}
