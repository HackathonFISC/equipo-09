"use client";

import { Button } from "@puente/ui/components/button";
import { Skeleton } from "@puente/ui/components/skeleton";
import { cn } from "@puente/ui/lib/utils";
import {
	CircleCheck,
	Hammer,
	Hourglass,
	RotateCw,
	SearchX,
	TriangleAlert,
	UserCheck,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AgentBadge, agentMeta } from "@/components/agents";
import { DataSourceNote } from "@/components/data-states";
import type {
	AgentName,
	AgentTrace,
	Trace,
	TraceStatus,
} from "@/lib/api/client";
import { loadTrace } from "@/lib/api/traces";
import { plural } from "@/lib/format";

/**
 * El contrato de `AgentTrace` aún no dice qué herramienta usó cada agente;
 * mientras tanto se muestra la herramienta que corresponde a su rol en el grafo.
 */
export const agentTool: Record<AgentName, string> = {
	supervisor: "Enrutador del grafo (LangGraph)",
	mercado: "LLM con taxonomía ESCO-lite",
	perfil: "LLM con extracción y evidencia",
	matching: "Solver OR-Tools CP-SAT",
	formacion: "Solver de formación (MIP o greedy)",
	postulacion: "LLM de redacción",
	entrevista: "LLM de entrevista",
	auditor: "Prueba contrafactual y reglas fijas",
	orientador: "Pausa del grafo (interrupt)",
};

const statusMeta: Record<
	TraceStatus,
	{ label: string; icon: typeof CircleCheck; tone: string }
> = {
	en_curso: {
		label: "En curso",
		icon: Hammer,
		tone: "border-primary/40 text-foreground",
	},
	esperando_revision: {
		label: "Esperando al orientador",
		icon: Hourglass,
		tone: "border-warning bg-warning/10 text-warning-fg",
	},
	completado: {
		label: "Completado",
		icon: CircleCheck,
		tone: "border-success/50 bg-success/5 text-success-fg",
	},
	error: {
		label: "Terminó con error",
		icon: TriangleAlert,
		tone: "border-danger/40 bg-danger/5 text-danger-fg",
	},
};

export function TraceStatusBadge({ status }: { status: TraceStatus }) {
	const { label, icon: Icon, tone } = statusMeta[status];
	return (
		<span
			className={cn(
				"inline-flex items-center gap-1.5 border px-2.5 py-1 font-medium text-sm",
				tone,
			)}
		>
			<Icon className="size-4" aria-hidden="true" />
			{label}
		</span>
	);
}

const time = new Intl.DateTimeFormat("es-PA", {
	hour: "2-digit",
	minute: "2-digit",
	second: "2-digit",
});

function seconds(ms: number) {
	return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function Field({
	label,
	children,
}: {
	label: string;
	children: React.ReactNode;
}) {
	return (
		<div className="flex flex-col gap-0.5">
			<dt className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
				{label}
			</dt>
			<dd className="text-pretty text-sm leading-relaxed">{children}</dd>
		</div>
	);
}

function StepCard({
	step,
	index,
	waiting,
}: {
	step: AgentTrace;
	index: number;
	/** Esta es la pausa HITL de un flujo que sigue detenido. */
	waiting: boolean;
}) {
	const human = step.agent === "orientador";
	const { icon: Icon, text, border } = agentMeta[step.agent];

	return (
		<li className="group relative grid grid-cols-[2rem_1fr] gap-x-3 pb-6 last:pb-0 sm:gap-x-4">
			<span
				aria-hidden="true"
				className="absolute top-8 bottom-0 left-4 w-px -translate-x-1/2 bg-border group-last:hidden"
			/>
			<span
				aria-hidden="true"
				className={cn(
					"tabular z-10 flex size-8 items-center justify-center border bg-background font-mono text-sm",
					human ? "border-warning text-warning-fg" : border,
				)}
			>
				{index + 1}
			</span>

			<article
				aria-label={`Paso ${index + 1}: ${agentMeta[step.agent].label}`}
				className={cn(
					"flex min-w-0 flex-col gap-3 border p-4",
					human && "border-2 border-warning bg-warning/10",
				)}
			>
				<header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
					<span className="flex flex-wrap items-center gap-2">
						<AgentBadge agent={step.agent} />
						{human ? (
							<span className="inline-flex items-center gap-1.5 font-semibold text-sm text-warning-fg">
								<UserCheck className="size-4" aria-hidden="true" />
								{waiting ? "Pausa: decide una persona" : "Decisión humana"}
							</span>
						) : null}
					</span>
					<span className="tabular font-mono text-muted-foreground text-xs">
						<time dateTime={step.createdAt}>
							{time.format(new Date(step.createdAt))}
						</time>
						{step.durationMs != null ? ` · ${seconds(step.durationMs)}` : null}
					</span>
				</header>

				<p className="text-balance font-semibold leading-snug">
					{step.decision}
				</p>

				<dl className="flex flex-col gap-3">
					{step.inputSummary ? (
						<Field label="Qué recibió">{step.inputSummary}</Field>
					) : null}
					<Field label="Herramienta">
						<span className="inline-flex items-center gap-1.5">
							<Icon
								className={cn("size-4 shrink-0", text)}
								aria-hidden="true"
							/>
							{agentTool[step.agent]}
						</span>
					</Field>
					{step.reason ? (
						<Field
							label={
								human
									? waiting
										? "Por qué se detiene"
										: "Qué se decidió y por qué"
									: "Por qué"
							}
						>
							{step.reason}
						</Field>
					) : null}
				</dl>
			</article>
		</li>
	);
}

type State =
	| { status: "loading" }
	| { status: "error"; message: string }
	| { status: "ready"; trace: Trace; source: "api" | "mock"; reason?: string };

const POLL_MS = 2500;

export function TraceView({ threadId }: { threadId: string }) {
	const [state, setState] = useState<State>({ status: "loading" });

	const load = useCallback(
		async (silent = false) => {
			if (!silent) setState({ status: "loading" });
			const r = await loadTrace(threadId);
			if (r.ok) {
				setState({
					status: "ready",
					trace: r.data,
					source: r.source,
					reason: r.reason,
				});
			} else if (!silent) {
				setState({ status: "error", message: r.message });
			}
		},
		[threadId],
	);

	useEffect(() => {
		void load();
	}, [load]);

	// Mientras el grafo corre, la traza crece: se vuelve a leer sola.
	const running = state.status === "ready" && state.trace.status === "en_curso";
	useEffect(() => {
		if (!running) return;
		const t = setInterval(() => void load(true), POLL_MS);
		return () => clearInterval(t);
	}, [running, load]);

	if (state.status === "loading") {
		return (
			<div className="flex flex-col gap-4">
				<output aria-live="polite" className="sr-only">
					Cargando la traza del flujo…
				</output>
				{["a", "b", "c"].map((k) => (
					<div key={k} className="grid grid-cols-[2rem_1fr] gap-x-3">
						<Skeleton className="size-8" />
						<div className="flex flex-col gap-3 border p-4">
							<Skeleton className="h-5 w-1/3" />
							<Skeleton className="h-5 w-3/4" />
							<Skeleton className="h-12 w-full" />
						</div>
					</div>
				))}
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
						No pudimos cargar la traza
					</p>
					<p>{state.message}</p>
					<p className="text-muted-foreground">
						Hilo: <span className="font-mono">{threadId}</span>
					</p>
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

	const { trace } = state;
	const steps = [...trace.steps].sort((a, b) => a.step - b.step);

	if (steps.length === 0) {
		return (
			<div className="flex flex-col items-center gap-3 border border-dashed px-6 py-12 text-center">
				<SearchX className="size-8 text-muted-foreground" aria-hidden="true" />
				<p className="font-medium">Este flujo aún no registró pasos</p>
				<p className="max-w-sm text-muted-foreground text-sm">
					Cuando un agente decida algo, aparecerá aquí con su explicación.
				</p>
			</div>
		);
	}

	const total = steps.reduce((sum, s) => sum + (s.durationMs ?? 0), 0);
	const waiting = trace.status === "esperando_revision";
	const lastHuman = steps.findLastIndex((s) => s.agent === "orientador");
	const agentCount = new Set(steps.map((s) => s.agent)).size;

	return (
		<div className="flex flex-col gap-6">
			<div className="flex flex-wrap items-center justify-between gap-3">
				<TraceStatusBadge status={trace.status} />
				<DataSourceNote source={state.source} reason={state.reason} />
			</div>

			{waiting ? (
				<div
					role="status"
					className="flex gap-3 border-2 border-warning bg-warning/10 p-4"
				>
					<Hourglass
						className="mt-0.5 size-5 shrink-0 text-warning-fg"
						aria-hidden="true"
					/>
					<div className="flex flex-col gap-1 text-sm">
						<p className="font-semibold">El flujo está detenido a propósito</p>
						<p className="text-pretty">
							Ningún agente sigue hasta que un orientador apruebe, edite o
							rechace la propuesta.
						</p>
						<Link
							href="/orientador"
							className="min-h-11 content-center text-primary underline underline-offset-4"
						>
							Ir a la bandeja del orientador
						</Link>
					</div>
				</div>
			) : null}

			{trace.status === "en_curso" ? (
				<output
					aria-live="polite"
					className="flex items-center gap-3 border border-dashed px-4 py-3 text-sm"
				>
					<Hammer
						className="size-5 shrink-0 animate-pulse"
						aria-hidden="true"
					/>
					Los agentes siguen trabajando; esta página se actualiza sola.
				</output>
			) : null}

			<p className="text-muted-foreground text-sm">
				{plural(steps.length, "paso", "pasos")} ·{" "}
				{plural(agentCount, "agente", "agentes")}
				{total > 0 ? ` · ${seconds(total)} de trabajo` : ""}
			</p>

			<ol className="flex flex-col">
				{steps.map((s, i) => (
					<StepCard
						key={`${s.step}-${s.agent}`}
						step={s}
						index={i}
						waiting={waiting && i === lastHuman}
					/>
				))}
			</ol>
		</div>
	);
}
