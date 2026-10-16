import { cn } from "@puente/ui/lib/utils";
import { FileText, MessagesSquare, UserCheck } from "lucide-react";

import type { ProfileSkill } from "@/lib/api/client";

const LEVEL = ["", "Básico", "Intermedio", "Avanzado"] as const;

const SOURCE: Record<
	ProfileSkill["source"],
	{ label: string; icon: typeof FileText }
> = {
	cv: { label: "De tu CV", icon: FileText },
	entrevista: { label: "De la entrevista", icon: MessagesSquare },
	orientador: { label: "Agregada por tu orientador", icon: UserCheck },
};

function LevelMeter({ level }: { level: number }) {
	return (
		<span className="inline-flex items-center gap-1.5 text-muted-foreground text-xs">
			<span aria-hidden="true" className="flex gap-0.5">
				{[1, 2, 3].map((n) => (
					<span
						key={n}
						className={cn(
							"h-2 w-3 border border-primary/50",
							n <= level && "bg-primary",
						)}
					/>
				))}
			</span>
			{LEVEL[level] ?? `Nivel ${level}`}
		</span>
	);
}

/** Habilidades del perfil con la frase que las justifica (evidencia). */
export function ProfileSkills({
	skills,
	highlight,
}: {
	skills: ProfileSkill[];
	/** Ids recién descubiertos, para marcarlos como nuevos. */
	highlight?: Set<string>;
}) {
	return (
		<ul className="flex flex-col border-y">
			{skills.map((s) => {
				const source = SOURCE[s.source];
				const isNew = highlight?.has(s.skill.id);
				return (
					<li
						key={s.skill.id}
						className="flex flex-col gap-2 border-b py-4 last:border-b-0"
					>
						<div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
							<span className="flex items-center gap-2 font-medium">
								{s.skill.labelEs}
								{isNew ? (
									<span className="border border-success/50 px-1.5 py-0.5 font-medium text-success-fg text-xs">
										Nueva
									</span>
								) : null}
							</span>
							<LevelMeter level={s.level} />
						</div>
						<blockquote className="border-agent-perfil/60 border-l-2 pl-3 text-sm">
							<mark className="bg-agent-perfil/10 text-foreground">
								«{s.evidence}»
							</mark>
						</blockquote>
						<span className="inline-flex items-center gap-1.5 text-muted-foreground text-xs">
							<source.icon className="size-3.5" aria-hidden="true" />
							{source.label}
						</span>
					</li>
				);
			})}
		</ul>
	);
}
