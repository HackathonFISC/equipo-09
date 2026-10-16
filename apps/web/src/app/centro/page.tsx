import { Button } from "@puente/ui/components/button";
import { BookOpen, Plus } from "lucide-react";
import type { Metadata } from "next";
import { connection } from "next/server";

import { DataSourceNote, ErrorState } from "@/components/data-states";
import { PageShell, RoleHeader } from "@/components/page-shell";
import { loadSkills } from "@/lib/api/catalog";
import type { Skill } from "@/lib/api/client";

export const metadata: Metadata = { title: "Cursos" };

function groupSkills(skills: Skill[]) {
	const groups = new Map<string, Skill[]>();
	for (const skill of skills) {
		const key = skill.group ?? "Sin grupo";
		groups.set(key, [...(groups.get(key) ?? []), skill]);
	}
	return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b, "es"));
}

export default async function CentroPage() {
	await connection();
	const skills = await loadSkills();

	return (
		<PageShell>
			<RoleHeader
				title="Cursos y sesiones"
				description="Registra cursos con las habilidades que enseñan y sus sesiones (cupos y horario). La ruta de formación los recomienda a jóvenes a quienes una habilidad les abre vacantes."
				actions={
					<Button size="lg" disabled title="Se habilita con el alta de cursos">
						<Plus aria-hidden="true" />
						Nuevo curso
					</Button>
				}
			/>

			<div className="flex flex-col items-center gap-3 border border-dashed px-6 py-12 text-center">
				<BookOpen className="size-8 text-muted-foreground" aria-hidden="true" />
				<p className="font-medium">Todavía no hay cursos cargados</p>
				<p className="max-w-md text-muted-foreground text-sm">
					Cuando registres un curso, aquí verás sus sesiones, los cupos ocupados
					y a los jóvenes que la ruta de formación sugiere inscribir.
				</p>
			</div>

			<section aria-labelledby="habilidades" className="flex flex-col gap-4">
				<div className="flex flex-wrap items-end justify-between gap-3">
					<div className="flex flex-col gap-1">
						<h2 id="habilidades" className="font-medium text-lg">
							Habilidades que un curso puede enseñar
						</h2>
						<p className="text-muted-foreground text-sm">
							Taxonomía ESCO-lite que usan el perfil y el matching.
						</p>
					</div>
					{skills.ok ? (
						<DataSourceNote source={skills.source} reason={skills.reason} />
					) : null}
				</div>

				{skills.ok ? (
					<dl className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
						{groupSkills(skills.data).map(([group, items]) => (
							<div key={group} className="flex flex-col gap-2 border-t pt-3">
								<dt className="font-medium text-sm">{group}</dt>
								<dd className="flex flex-wrap gap-1.5">
									{items.map((s) => (
										<span key={s.id} className="border px-2 py-0.5 text-xs">
											{s.labelEs}
										</span>
									))}
								</dd>
							</div>
						))}
					</dl>
				) : (
					<ErrorState
						title="No pudimos cargar las habilidades"
						message={skills.message}
					/>
				)}
			</section>
		</PageShell>
	);
}
