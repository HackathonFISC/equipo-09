"use client";

import { Button } from "@puente/ui/components/button";
import { Skeleton } from "@puente/ui/components/skeleton";
import { cn } from "@puente/ui/lib/utils";
import {
	Building2,
	CalendarClock,
	CalendarX,
	CircleCheck,
	Clock,
	GraduationCap,
	RotateCw,
	Target,
	Timer,
	TriangleAlert,
	Wallet,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { AgentWorking } from "@/components/agents";
import { DataSourceNote } from "@/components/data-states";
import { TraceLink } from "@/components/trace-link";
import type { Course, Skill, TrainingPlan } from "@/lib/api/client";
import { loadOpportunities } from "@/lib/api/reviews";
import {
	loadTrainingPlan,
	MOCK_PLAN_THREAD,
	type PlanView,
	requestTrainingPlan,
} from "@/lib/api/traces";
import { formatSchedule, plural } from "@/lib/format";
import { rememberYouth } from "@/lib/youth-session";

type Item = TrainingPlan["items"][number];

type State =
	| { status: "loading" }
	| { status: "error"; message: string }
	/** El joven aún no tiene ruta: se ofrece calcularla (no es un error). */
	| { status: "empty" }
	| {
			status: "ready";
			view: PlanView;
			source: "api" | "mock";
			reason?: string;
			/** Habilidades que las ofertas le piden y aún no tiene (minúsculas). */
			gaps: Set<string>;
	  };

const norm = (s: string) => s.trim().toLowerCase();

const dateFmt = new Intl.DateTimeFormat("es-PA", { dateStyle: "long" });
const formatDate = (iso: string) => dateFmt.format(new Date(`${iso}T00:00:00`));
const money = (n: number) => `B/. ${n.toFixed(2)}`;

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

/** Cruza el ítem del plan con su curso (por título) y las habilidades que enseña. */
function describe(item: Item, view: PlanView) {
	const course: Course | undefined = view.courses.find(
		(c) => norm(c.title) === norm(item.courseTitle),
	);
	const skills: Skill[] = (course?.skillIds ?? [])
		.map((id) => view.skills.find((s) => s.id === id))
		.filter((s): s is Skill => Boolean(s));
	return {
		course,
		skills,
		center: course ? view.centers[course.centerId] : undefined,
	};
}

function CourseCard({
	item,
	index,
	view,
	gaps,
}: {
	item: Item;
	index: number;
	view: PlanView;
	gaps: Set<string>;
}) {
	const { course, skills, center } = describe(item, view);
	const { session } = item;
	const schedule = formatSchedule(session.schedule);
	const free = session.seatsTotal - (session.seatsTaken ?? 0);
	const closing = skills.filter((s) => gaps.has(norm(s.labelEs)));

	return (
		<li className="grid grid-cols-[2rem_1fr] gap-x-3 sm:gap-x-4">
			<span
				aria-hidden="true"
				className="tabular z-10 flex size-8 items-center justify-center border border-agent-formacion/60 bg-background font-mono text-sm"
			>
				{index + 1}
			</span>
			<article
				aria-label={`Curso ${index + 1}: ${item.courseTitle}`}
				className="flex min-w-0 flex-col gap-4 border p-4"
			>
				<header className="flex flex-col gap-1">
					<h3 className="text-balance font-semibold text-lg leading-snug">
						{item.courseTitle}
					</h3>
					{center ? (
						<p className="inline-flex items-center gap-1.5 text-muted-foreground text-sm">
							<Building2 className="size-4 shrink-0" aria-hidden="true" />
							{center}
						</p>
					) : null}
				</header>

				<ul
					aria-label="Duración, costo y horario"
					className="flex flex-wrap gap-2"
				>
					{course ? (
						<>
							<Chip icon={Clock}>
								<span className="tabular font-mono">{course.hours} h</span>
								<span className="sr-only"> de duración</span>
							</Chip>
							<Chip icon={Wallet}>
								<span className="tabular font-mono">{money(course.cost)}</span>
							</Chip>
						</>
					) : null}
					{schedule ? <Chip icon={CalendarClock}>{schedule}</Chip> : null}
					{item.commuteMin != null ? (
						<Chip icon={Timer}>
							<span className="tabular font-mono">{item.commuteMin} min</span>
							<span> de viaje</span>
						</Chip>
					) : null}
					<Chip
						icon={free > 0 ? CircleCheck : CalendarX}
						tone={free > 0 ? "good" : "bad"}
					>
						{free > 0
							? `${plural(free, "cupo libre", "cupos libres")}`
							: "Sin cupos"}
					</Chip>
				</ul>

				<p className="text-muted-foreground text-sm">
					Empieza el{" "}
					<time dateTime={session.startDate}>
						{formatDate(session.startDate)}
					</time>
					.
				</p>

				<section
					aria-label="Qué brecha cierra"
					className="flex flex-col gap-1.5 border-agent-formacion border-l-2 bg-muted/40 px-4 py-3"
				>
					<h4 className="flex items-center gap-1.5 font-medium text-muted-foreground text-xs uppercase tracking-wide">
						<Target className="size-3.5" aria-hidden="true" />
						Qué brecha cierra
					</h4>
					{skills.length > 0 ? (
						<ul className="flex flex-wrap gap-1.5">
							{skills.map((s) => {
								const isGap = gaps.has(norm(s.labelEs));
								return (
									<li
										key={s.id}
										className={cn(
											"border px-2 py-0.5 text-sm",
											isGap && "border-success/50 bg-success/10 font-medium",
										)}
									>
										{s.labelEs}
										{isGap ? (
											<span className="sr-only"> (te la piden)</span>
										) : null}
									</li>
								);
							})}
						</ul>
					) : (
						<p className="text-muted-foreground text-sm">
							La API todavía no dice qué habilidad enseña este curso.
						</p>
					)}
					{closing.length > 0 ? (
						<p className="text-pretty text-sm">
							Las ofertas que viste piden{" "}
							<strong className="font-medium">
								{closing.map((s) => s.labelEs).join(", ")}
							</strong>
							. Este curso te la da.
						</p>
					) : null}
				</section>
			</article>
		</li>
	);
}

export function TrainingRoute({ youthId }: { youthId: string }) {
	const [state, setState] = useState<State>({ status: "loading" });
	const [threadId, setThreadId] = useState<string | null>(null);
	const [computing, setComputing] = useState(false);
	const [computeError, setComputeError] = useState<string | null>(null);

	const load = useCallback(async () => {
		setState({ status: "loading" });
		const [plan, opps] = await Promise.all([
			loadTrainingPlan(youthId),
			loadOpportunities(youthId),
		]);
		if (!plan.ok) {
			setState({ status: "error", message: plan.message });
			return;
		}
		rememberYouth(youthId);
		if (plan.data === null) {
			setState({ status: "empty" });
			return;
		}
		const view = plan.data;
		const gaps = new Set<string>();
		if (opps.ok) {
			for (const o of opps.data) {
				for (const m of o.match.scoreBreakdown.missingSkills ?? []) {
					gaps.add(norm(m));
				}
			}
		}
		if (plan.source === "mock") setThreadId(MOCK_PLAN_THREAD);
		setState({
			status: "ready",
			view,
			source: plan.source,
			reason: plan.reason,
			gaps,
		});
	}, [youthId]);

	useEffect(() => {
		void load();
	}, [load]);

	async function compute(simulated: boolean) {
		setComputing(true);
		setComputeError(null);
		const r = await requestTrainingPlan(youthId, { simulated });
		if (r.ok) {
			setThreadId(r.data.threadId);
			await load();
		} else {
			setComputeError(r.message);
		}
		setComputing(false);
	}

	if (state.status === "loading") {
		return (
			<div className="flex flex-col gap-4">
				<output aria-live="polite" className="sr-only">
					Formación está armando tu ruta…
				</output>
				<Skeleton className="h-24 w-full" />
				{["a", "b"].map((k) => (
					<div key={k} className="grid grid-cols-[2rem_1fr] gap-x-3">
						<Skeleton className="size-8" />
						<div className="flex flex-col gap-3 border p-4">
							<Skeleton className="h-6 w-3/4" />
							<Skeleton className="h-8 w-full" />
							<Skeleton className="h-16 w-full" />
						</div>
					</div>
				))}
			</div>
		);
	}

	if (state.status === "empty") {
		return (
			<div className="flex flex-col items-center gap-3 border border-dashed px-6 py-12 text-center">
				<GraduationCap
					className="size-8 text-muted-foreground"
					aria-hidden="true"
				/>
				<p className="font-medium">Todavía no tienes una ruta de formación</p>
				<p className="max-w-sm text-muted-foreground text-sm">
					Formación compara tus habilidades con las ofertas a tu alcance y elige
					los cursos que más vacantes te abren, sin chocar con tu horario ni tu
					presupuesto.
				</p>
				{computing ? (
					<AgentWorking agent="formacion">
						Formación está armando tu ruta…
					</AgentWorking>
				) : (
					<Button
						size="lg"
						className="h-11"
						onClick={() => void compute(false)}
					>
						Calcular mi ruta
					</Button>
				)}
				{computeError ? (
					<p role="alert" className="text-danger-fg text-sm">
						{computeError}
					</p>
				) : null}
			</div>
		);
	}

	if (state.status === "error") {
		return (
			<div className="flex flex-col items-start gap-3">
				<div
					role="alert"
					className="flex flex-col gap-1 border border-danger/40 bg-danger/5 p-4 text-sm"
				>
					<p className="flex items-center gap-2 font-medium text-danger-fg">
						<TriangleAlert className="size-4 shrink-0" aria-hidden="true" />
						No pudimos cargar tu ruta de formación
					</p>
					<p>{state.message}</p>
				</div>
				<Button
					variant="outline"
					size="lg"
					className="h-11"
					onClick={() => void load()}
				>
					<RotateCw aria-hidden="true" />
					Reintentar
				</Button>
			</div>
		);
	}

	const { view, source, reason, gaps } = state;
	const { plan } = view;
	const items = [...plan.items].sort((a, b) =>
		a.session.startDate.localeCompare(b.session.startDate),
	);

	if (items.length === 0) {
		return (
			<div className="flex flex-col gap-4">
				<DataSourceNote source={source} reason={reason} />
				<div className="flex flex-col items-center gap-3 border border-dashed px-6 py-12 text-center">
					<GraduationCap
						className="size-8 text-muted-foreground"
						aria-hidden="true"
					/>
					<p className="font-medium">Por ahora no necesitas más cursos</p>
					<p className="max-w-sm text-muted-foreground text-sm">
						{plan.explanation ||
							"Tus habilidades ya cubren las ofertas a tu alcance. Si aparece una oferta que te pide algo nuevo, Formación te arma una ruta."}
					</p>
					{computing ? (
						<AgentWorking agent="formacion">
							Formación está recalculando…
						</AgentWorking>
					) : (
						<Button
							size="lg"
							className="h-11"
							onClick={() => void compute(source === "mock")}
						>
							Recalcular mi ruta
						</Button>
					)}
				</div>
			</div>
		);
	}

	return (
		<div className="flex flex-col gap-6">
			<DataSourceNote source={source} reason={reason} />

			<dl className="grid grid-cols-3 border">
				<div className="flex flex-col gap-0.5 border-r p-3">
					<dt className="text-muted-foreground text-xs">Cursos</dt>
					<dd className="tabular font-mono font-semibold text-xl">
						{items.length}
					</dd>
				</div>
				<div className="flex flex-col gap-0.5 border-r p-3">
					<dt className="text-muted-foreground text-xs">Costo total</dt>
					<dd className="tabular font-mono font-semibold text-xl">
						{money(plan.totalCost)}
					</dd>
				</div>
				<div className="flex flex-col gap-0.5 p-3">
					<dt className="text-muted-foreground text-xs">Ofertas que abre</dt>
					<dd className="tabular font-mono font-semibold text-success-fg text-xl">
						{plan.unlockedPostings}
					</dd>
				</div>
			</dl>

			<section
				aria-labelledby="por-que-ruta"
				className="flex flex-col gap-1.5 border-primary border-l-2 bg-muted/40 px-4 py-3"
			>
				<h2
					id="por-que-ruta"
					className="font-medium text-muted-foreground text-xs uppercase tracking-wide"
				>
					Por qué esta ruta
				</h2>
				<p className="text-pretty text-sm leading-relaxed">
					{plan.explanation}
				</p>
			</section>

			<section aria-labelledby="cursos" className="flex flex-col gap-3">
				<h2 id="cursos" className="font-medium text-sm">
					{plural(
						items.length,
						"curso, en este orden",
						"cursos, en este orden",
					)}
				</h2>
				<ol className="flex flex-col gap-4">
					{items.map((item, i) => (
						<CourseCard
							key={`${item.courseTitle}-${item.session.startDate}`}
							item={item}
							index={i}
							view={view}
							gaps={gaps}
						/>
					))}
				</ol>
			</section>

			{computeError ? (
				<p role="alert" className="text-danger-fg text-sm">
					{computeError}
				</p>
			) : null}

			<div className="flex flex-col border-y sm:flex-row sm:items-center sm:gap-6">
				{threadId ? (
					<TraceLink threadId={threadId}>
						Ver cómo Formación eligió estos cursos
					</TraceLink>
				) : null}
				<Button
					variant="ghost"
					size="lg"
					className="h-11 justify-start"
					disabled={computing}
					onClick={() => void compute(source === "mock")}
				>
					<RotateCw
						className={computing ? "animate-spin" : undefined}
						aria-hidden="true"
					/>
					{computing ? "Recalculando…" : "Recalcular mi ruta"}
				</Button>
			</div>
		</div>
	);
}
