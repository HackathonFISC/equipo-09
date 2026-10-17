import { Button } from "@puente/ui/components/button";
import { BookOpen, Plus } from "lucide-react";
import type { Metadata } from "next";
import { connection } from "next/server";

import { DataSourceNote, ErrorState } from "@/components/data-states";
import { PageShell, RoleHeader } from "@/components/page-shell";
import { loadCourses, loadSkills } from "@/lib/api/catalog";
import type { Skill } from "@/lib/api/client";
import { formatSchedule, skillGroupLabel } from "@/lib/format";

export const metadata: Metadata = { title: "Cursos" };

function groupSkills(skills: Skill[]) {
	const groups = new Map<string, Skill[]>();
	for (const skill of skills) {
		const key = skillGroupLabel(skill.group);
		groups.set(key, [...(groups.get(key) ?? []), skill]);
	}
	return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b, "es"));
}

export default async function CentroPage() {
	await connection();
	const [skills, courses] = await Promise.all([loadSkills(), loadCourses()]);

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

			<section aria-labelledby="cursos" className="flex flex-col gap-4">
				<div className="flex flex-wrap items-end justify-between gap-3">
					<div className="flex flex-col gap-1">
						<h2 id="cursos" className="font-medium text-lg">
							Cursos con sesiones
						</h2>
						<p className="text-muted-foreground text-sm">
							Los cupos libres son los que la ruta de formación puede usar para
							inscribir a jóvenes.
						</p>
					</div>
					{courses.ok ? (
						<DataSourceNote source={courses.source} reason={courses.reason} />
					) : null}
				</div>
				{courses.ok && courses.data.length > 0 ? (
					<ul className="grid gap-4 md:grid-cols-2">
						{courses.data.map((c) => (
							<li key={c.id} className="flex flex-col gap-3 border p-4">
								<div className="flex flex-col gap-1">
									<h3 className="text-balance font-semibold leading-snug">
										{c.title}
									</h3>
									<p className="tabular font-mono text-muted-foreground text-sm">
										{c.hours} h · B/. {c.cost.toFixed(2)}
									</p>
								</div>
								<ul className="flex flex-col gap-1.5 text-sm">
									{c.sessions.map((s) => {
										const free = s.seatsTotal - (s.seatsTaken ?? 0);
										return (
											<li
												key={s.id ?? s.startDate}
												className="flex flex-wrap items-baseline justify-between gap-x-3 border-t pt-1.5"
											>
												<span>
													{formatSchedule(s.schedule)}
													<span className="text-muted-foreground">
														{" "}
														· desde el {s.startDate}
													</span>
												</span>
												<span
													className={
														free > 0
															? "tabular font-mono"
															: "tabular font-mono text-danger-fg"
													}
												>
													{free > 0
														? `${free} de ${s.seatsTotal} cupos`
														: "Sin cupos"}
												</span>
											</li>
										);
									})}
								</ul>
							</li>
						))}
					</ul>
				) : courses.ok ? (
					<div className="flex flex-col items-center gap-3 border border-dashed px-6 py-12 text-center">
						<BookOpen
							className="size-8 text-muted-foreground"
							aria-hidden="true"
						/>
						<p className="font-medium">Todavía no hay cursos cargados</p>
						<p className="max-w-md text-muted-foreground text-sm">
							Cuando registres un curso, aquí verás sus sesiones y los cupos
							ocupados.
						</p>
					</div>
				) : (
					<ErrorState
						title="No pudimos cargar los cursos"
						message={courses.message}
					/>
				)}
			</section>

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
