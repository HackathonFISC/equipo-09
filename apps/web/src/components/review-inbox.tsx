"use client";

import { Button } from "@puente/ui/components/button";
import { Label } from "@puente/ui/components/label";
import { Skeleton } from "@puente/ui/components/skeleton";
import { cn } from "@puente/ui/lib/utils";
import {
	Ban,
	CircleCheck,
	ListOrdered,
	MousePointerClick,
	RotateCw,
	Scale,
	TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { AgentBadge } from "@/components/agents";
import { DataSourceNote } from "@/components/data-states";
import { ReviewDetail, ReviewStatusBadge } from "@/components/review-detail";
import type {
	AgentTrace,
	ReviewKind,
	ReviewStatus,
	ReviewTask,
} from "@/lib/api/client";
import { loadReviews, type Result } from "@/lib/api/reviews";
import { plural } from "@/lib/format";
import {
	impactOf,
	kindMeta,
	parseProposal,
	timeAgo,
} from "@/lib/review-proposal";

const kindIcon = {
	bloqueo_oferta: Ban,
	lista_corta: ListOrdered,
	alerta_sesgo: Scale,
} as const satisfies Record<ReviewKind, unknown>;

type Tab = "pendientes" | "resueltas";
const isPending = (s: ReviewStatus) => s === "pendiente";

type Loaded = {
	status: "ready";
	tasks: ReviewTask[];
	source: Extract<Result<ReviewTask[]>, { ok: true }>["source"];
	reason?: string;
};
type State =
	| { status: "loading" }
	| { status: "error"; message: string }
	| Loaded;

export function ReviewInbox() {
	const [state, setState] = useState<State>({ status: "loading" });
	const [tab, setTab] = useState<Tab>("pendientes");
	const [kind, setKind] = useState<ReviewKind | "todas">("todas");
	const [selectedId, setSelectedId] = useState<string | null>(null);
	const headingRef = useRef<HTMLHeadingElement>(null);
	const focusDetail = useRef(false);
	const kindId = useId();

	const load = useCallback(async () => {
		setState({ status: "loading" });
		const r = await loadReviews();
		setState(
			r.ok
				? { status: "ready", tasks: r.data, source: r.source, reason: r.reason }
				: { status: "error", message: r.message },
		);
	}, []);

	useEffect(() => {
		void load();
	}, [load]);

	useEffect(() => {
		if (selectedId && focusDetail.current) {
			focusDetail.current = false;
			headingRef.current?.focus();
		}
	}, [selectedId]);

	if (state.status === "loading") {
		return (
			<div className="flex flex-col gap-3">
				<output aria-live="polite" className="sr-only">
					Cargando la bandeja de revisión…
				</output>
				<Skeleton className="h-9 w-64" />
				{["a", "b", "c"].map((k) => (
					<Skeleton key={k} className="h-14 w-full" />
				))}
			</div>
		);
	}

	if (state.status === "error") {
		return (
			<div
				role="alert"
				className="flex flex-col items-start gap-3 border border-danger/40 bg-danger/5 p-6"
			>
				<p className="flex items-center gap-2 font-medium text-danger-fg">
					<TriangleAlert className="size-5 shrink-0" aria-hidden="true" />
					No pudimos cargar la bandeja
				</p>
				<p className="text-muted-foreground text-sm">
					{state.message} Las decisiones pendientes siguen esperando; revise que
					la API esté corriendo e inténtelo de nuevo.
				</p>
				<Button variant="outline" size="lg" className="h-11" onClick={load}>
					<RotateCw aria-hidden="true" />
					Reintentar
				</Button>
			</div>
		);
	}

	const simulated = state.source === "mock";
	const sorted = [...state.tasks].sort(
		(a, b) => +new Date(b.createdAt) - +new Date(a.createdAt),
	);
	const pendingCount = sorted.filter((t) => isPending(t.status)).length;
	const resolvedCount = sorted.length - pendingCount;
	const visible = sorted.filter(
		(t) =>
			(tab === "pendientes") === isPending(t.status) &&
			(kind === "todas" || t.kind === kind),
	);
	const selected = state.tasks.find((t) => t.id === selectedId) ?? null;

	function select(id: string) {
		focusDetail.current = true;
		setSelectedId(id);
	}

	function onDecided(resolved: ReviewTask) {
		setState((prev) =>
			prev.status === "ready"
				? {
						...prev,
						tasks: prev.tasks.map((t) => (t.id === resolved.id ? resolved : t)),
					}
				: prev,
		);
		focusDetail.current = true;
		setSelectedId(resolved.id);
	}

	return (
		<div className="flex flex-col gap-4">
			<div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
				<fieldset className="m-0 flex min-w-0 border p-0">
					<legend className="sr-only">Estado de las revisiones</legend>
					{(
						[
							["pendientes", `Pendientes (${pendingCount})`],
							["resueltas", `Resueltas (${resolvedCount})`],
						] as const
					).map(([id, label]) => (
						<button
							key={id}
							type="button"
							aria-pressed={tab === id}
							onClick={() => setTab(id)}
							className={cn(
								"h-11 px-4 font-medium text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset",
								tab === id
									? "bg-primary text-primary-foreground"
									: "hover:bg-muted",
							)}
						>
							{label}
						</button>
					))}
				</fieldset>
				<div className="flex items-center gap-2">
					<Label htmlFor={kindId} className="text-sm">
						Tipo
					</Label>
					<select
						id={kindId}
						value={kind}
						onChange={(e) => setKind(e.target.value as ReviewKind | "todas")}
						className="h-11 border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
					>
						<option value="todas">Todos</option>
						{(Object.keys(kindMeta) as ReviewKind[]).map((k) => (
							<option key={k} value={k}>
								{kindMeta[k].label}
							</option>
						))}
					</select>
					<Button
						variant="outline"
						size="lg"
						className="h-11"
						onClick={load}
						aria-label="Actualizar bandeja"
					>
						<RotateCw aria-hidden="true" />
						Actualizar
					</Button>
				</div>
			</div>

			<DataSourceNote source={state.source} reason={state.reason} />

			<div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
				<section aria-labelledby="lista-titulo" className="flex flex-col gap-2">
					<h2 id="lista-titulo" className="font-medium text-sm">
						{tab === "pendientes"
							? plural(visible.length, "decisión espera", "decisiones esperan")
							: plural(
									visible.length,
									"decisión resuelta",
									"decisiones resueltas",
								)}
						{tab === "pendientes" ? " su visto bueno" : ""}
					</h2>
					{visible.length === 0 ? (
						<EmptyList tab={tab} filtered={kind !== "todas"} />
					) : (
						<div className="overflow-x-auto border">
							<table className="w-full min-w-[28rem] text-sm">
								<thead className="bg-muted/60 text-left text-muted-foreground">
									<tr>
										<th scope="col" className="px-3 py-2 font-medium">
											Tipo
										</th>
										<th scope="col" className="px-3 py-2 font-medium">
											Agente
										</th>
										<th scope="col" className="px-3 py-2 font-medium">
											Impacto
										</th>
										<th scope="col" className="px-3 py-2 font-medium">
											{tab === "pendientes" ? "Antigüedad" : "Estado"}
										</th>
									</tr>
								</thead>
								<tbody>
									{visible.map((t) => {
										const p = parseProposal(t);
										const Icon = kindIcon[t.kind];
										const active = t.id === selectedId;
										const agent = t.agent as AgentTrace["agent"] | undefined;
										return (
											<tr
												key={t.id}
												className={cn(
													"border-t align-top",
													active && "bg-muted/60",
												)}
											>
												<td className="px-3 py-2.5">
													<button
														type="button"
														onClick={() => select(t.id)}
														aria-pressed={active}
														className="-m-1 flex min-h-11 w-full items-start gap-2 p-1 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
													>
														<Icon
															className="mt-0.5 size-4 shrink-0 text-warning-fg"
															aria-hidden="true"
														/>
														<span className="flex flex-col">
															<span className="font-medium">
																{kindMeta[t.kind].label}
															</span>
															{p.subject ? (
																<span className="text-muted-foreground">
																	{p.subject}
																</span>
															) : null}
														</span>
													</button>
												</td>
												<td className="px-3 py-2.5">
													{agent ? (
														<AgentBadge agent={agent} />
													) : (
														<span className="text-muted-foreground">—</span>
													)}
												</td>
												<td className="px-3 py-2.5">{impactOf(t, p)}</td>
												<td className="px-3 py-2.5">
													{tab === "pendientes" ? (
														<span className="tabular whitespace-nowrap font-mono text-xs">
															{timeAgo(t.createdAt)}
														</span>
													) : (
														<ReviewStatusBadge status={t.status} />
													)}
												</td>
											</tr>
										);
									})}
								</tbody>
							</table>
						</div>
					)}
				</section>

				<div className="xl:sticky xl:top-20">
					{selected ? (
						<ReviewDetail
							key={selected.id}
							task={selected}
							simulated={simulated}
							onDecided={onDecided}
							headingRef={headingRef}
						/>
					) : (
						<div className="flex flex-col items-center gap-2 border border-dashed px-6 py-14 text-center">
							<MousePointerClick
								className="size-7 text-muted-foreground"
								aria-hidden="true"
							/>
							<p className="font-medium">Elija una decisión para revisarla</p>
							<p className="max-w-sm text-muted-foreground text-sm">
								Verá la propuesta del agente, por qué la hace, la traza del
								flujo y los botones para aprobar, editar o rechazar.
							</p>
						</div>
					)}
				</div>
			</div>
		</div>
	);
}

function EmptyList({ tab, filtered }: { tab: Tab; filtered: boolean }) {
	return (
		<div className="flex flex-col items-center gap-2 border px-6 py-12 text-center">
			<CircleCheck className="size-6 text-success-fg" aria-hidden="true" />
			<p className="font-medium">
				{tab === "pendientes"
					? "No hay decisiones pendientes"
					: "Aún no hay decisiones resueltas"}
			</p>
			<p className="max-w-md text-muted-foreground text-sm">
				{filtered
					? "Ninguna coincide con el tipo elegido. Pruebe con «Todos»."
					: tab === "pendientes"
						? "Cuando un agente necesite su visto bueno, la tarea aparecerá aquí y el flujo esperará su decisión."
						: "Las decisiones que tome quedan registradas aquí con su comentario."}
			</p>
		</div>
	);
}
