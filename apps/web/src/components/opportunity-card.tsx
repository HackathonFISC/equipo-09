import { cn } from "@puente/ui/lib/utils";
import {
	CalendarCheck,
	CalendarX,
	CircleCheck,
	Clock,
	MapPin,
	Timer,
	Wallet,
} from "lucide-react";

import type { Opportunity } from "@/lib/api/reviews";
import { formatSalary, formatSchedule } from "@/lib/format";

const pct = (v: number) => `${Math.round(Math.min(Math.max(v, 0), 1) * 100)} %`;

/** Sin color como único indicador: el número siempre acompaña a la barra. */
function Bar({ value, className }: { value: number; className?: string }) {
	return (
		<span
			aria-hidden="true"
			className="block h-2 w-full overflow-hidden bg-muted"
		>
			<span
				className={cn("block h-full bg-primary", className)}
				style={{ width: pct(value) }}
			/>
		</span>
	);
}

function Chip({
	icon: Icon,
	tone = "neutral",
	children,
}: {
	icon: typeof Timer;
	tone?: "neutral" | "good" | "bad";
	children: React.ReactNode;
}) {
	return (
		<li
			className={cn(
				"inline-flex min-h-8 items-center gap-1.5 border px-2.5 py-1 text-sm",
				tone === "good" && "border-success/40 bg-success/5",
				tone === "bad" && "border-danger/40 bg-danger/5 text-danger-fg",
			)}
		>
			<Icon className="size-4 shrink-0" aria-hidden="true" />
			{children}
		</li>
	);
}

const BREAKDOWN = [
	["skillCoverage", "Habilidades que ya tienes"],
	["commute", "Cercanía"],
	["cost", "Pasaje accesible"],
	["schedule", "Horario compatible"],
	["salary", "Salario"],
] as const;

export function OpportunityCard({
	opportunity: { match, posting },
}: {
	opportunity: Opportunity;
}) {
	const { scoreBreakdown: sb, constraintsChecked: c } = match;
	const reviewed = match.status === "aprobado";
	const salary = posting
		? formatSalary(posting.salaryMin, posting.salaryMax)
		: null;
	const schedule = posting ? formatSchedule(posting.schedule) : null;
	const missing = sb.missingSkills ?? [];

	return (
		<li className="flex flex-col gap-4 border p-4">
			<header className="flex flex-col gap-1">
				<h3 className="text-balance font-semibold text-lg leading-snug">
					{posting?.title ?? "Oferta de trabajo"}
				</h3>
				<div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-sm">
					<span className="inline-flex items-center gap-1.5 text-muted-foreground">
						<MapPin className="size-4 shrink-0" aria-hidden="true" />
						{posting?.location
							? `${posting.location.corregimiento}, ${posting.location.distrito}`
							: "Ubicación por confirmar"}
					</span>
					<span
						className={cn(
							"inline-flex items-center gap-1 font-medium",
							reviewed ? "text-success-fg" : "text-warning-fg",
						)}
					>
						{reviewed ? (
							<CircleCheck className="size-4" aria-hidden="true" />
						) : (
							<Clock className="size-4" aria-hidden="true" />
						)}
						{reviewed
							? "Revisada por un orientador"
							: "Un orientador la está revisando"}
					</span>
				</div>
			</header>

			<ul aria-label="Lo que te cuesta llegar" className="flex flex-wrap gap-2">
				<Chip icon={Timer}>
					<span className="tabular font-mono">{c.commuteMin} min</span>
					<span className="sr-only"> de viaje</span>
				</Chip>
				<Chip icon={Wallet}>
					<span className="tabular font-mono">
						B/. {c.dailyCost.toFixed(2)}
					</span>
					<span>/día</span>
				</Chip>
				<Chip
					icon={c.scheduleOverlap ? CalendarCheck : CalendarX}
					tone={c.scheduleOverlap ? "good" : "bad"}
				>
					{c.scheduleOverlap ? "Horario compatible" : "Horario no compatible"}
				</Chip>
				<Chip icon={Wallet} tone={c.salaryOk ? "neutral" : "bad"}>
					{salary ? (
						<span className="tabular font-mono">{salary}</span>
					) : c.salaryOk ? (
						"Salario dentro de tu rango"
					) : (
						"Salario bajo tu mínimo"
					)}
				</Chip>
			</ul>

			<div className="flex flex-col gap-1.5">
				<p className="flex items-baseline justify-between gap-2 text-sm">
					<span className="font-medium">Habilidades que ya tienes</span>
					<span className="tabular font-mono">{pct(sb.skillCoverage)}</span>
				</p>
				<Bar value={sb.skillCoverage} />
				{missing.length > 0 ? (
					<p className="text-sm">
						<span className="font-medium text-warning-fg">Te falta: </span>
						{missing.join(", ")}
					</p>
				) : null}
			</div>

			<section aria-label="Por qué encajas" className="flex flex-col gap-1">
				<h4 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
					Por qué encajas
				</h4>
				<p className="text-pretty text-sm leading-relaxed">
					{match.explanation}
				</p>
			</section>

			<details className="group border-t pt-3">
				<summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 font-medium text-primary text-sm underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring/50 [&::-webkit-details-marker]:hidden">
					<span>Ver cómo se calculó</span>
					<span
						aria-hidden="true"
						className="text-muted-foreground transition-transform group-open:rotate-180"
					>
						▾
					</span>
				</summary>
				<div className="flex flex-col gap-3 pt-2">
					<dl className="flex flex-col gap-2.5">
						{BREAKDOWN.map(([key, label]) => (
							<div key={key} className="flex flex-col gap-1">
								<div className="flex items-baseline justify-between gap-2 text-sm">
									<dt>{label}</dt>
									<dd className="tabular font-mono">{pct(sb[key])}</dd>
								</div>
								<Bar value={sb[key]} />
							</div>
						))}
					</dl>
					{schedule ? (
						<p className="text-muted-foreground text-sm">
							Horario de la oferta:{" "}
							<span className="tabular font-mono">{schedule}</span>
						</p>
					) : null}
					<p className="text-muted-foreground text-xs">
						Estos porcentajes los calcula el solver con reglas fijas. La frase
						de arriba solo los explica con palabras.
					</p>
				</div>
			</details>
		</li>
	);
}
