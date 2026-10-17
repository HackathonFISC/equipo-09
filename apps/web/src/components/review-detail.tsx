"use client";

import { Button } from "@puente/ui/components/button";
import { Input } from "@puente/ui/components/input";
import { Label } from "@puente/ui/components/label";
import { Skeleton } from "@puente/ui/components/skeleton";
import { Textarea } from "@puente/ui/components/textarea";
import { cn } from "@puente/ui/lib/utils";
import {
	ArrowDown,
	ArrowUp,
	Ban,
	CircleCheck,
	Clock,
	Pencil,
	TriangleAlert,
	Undo2,
	X,
} from "lucide-react";
import { useEffect, useId, useState } from "react";
import { toast } from "sonner";

import { AgentBadge, TraceSteps } from "@/components/agents";
import { ScheduledInterviews } from "@/components/scheduled-interviews";
import { TraceLink } from "@/components/trace-link";
import type {
	AgentTrace,
	ReviewDecision,
	ReviewStatus,
	ReviewTask,
} from "@/lib/api/client";
import { decideReview, loadReviewTrace } from "@/lib/api/reviews";
import {
	type BiasPair,
	type Candidate,
	kindMeta,
	type ParsedProposal,
	parseProposal,
	timeAgo,
} from "@/lib/review-proposal";

export const statusMeta: Record<
	ReviewStatus,
	{ label: string; icon: typeof Clock; className: string }
> = {
	pendiente: { label: "Pendiente", icon: Clock, className: "text-warning-fg" },
	aprobada: {
		label: "Aprobada",
		icon: CircleCheck,
		className: "text-success-fg",
	},
	editada: {
		label: "Editada y aprobada",
		icon: Pencil,
		className: "text-success-fg",
	},
	rechazada: { label: "Rechazada", icon: Ban, className: "text-danger-fg" },
};

export function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
	const { label, icon: Icon, className } = statusMeta[status];
	return (
		<span
			className={cn(
				"inline-flex items-center gap-1 font-medium text-sm",
				className,
			)}
		>
			<Icon className="size-4" aria-hidden="true" />
			{label}
		</span>
	);
}

const REVIEWER_KEY = "puente:reviewer";

function recallReviewer() {
	try {
		return localStorage.getItem(REVIEWER_KEY) ?? "";
	} catch {
		return "";
	}
}

function rememberReviewer(name: string) {
	try {
		localStorage.setItem(REVIEWER_KEY, name);
	} catch {
		// Almacenamiento bloqueado: se vuelve a escribir la próxima vez.
	}
}

const pct = (v: number) => `${Math.round(v * 100)} %`;
const money = (v: number) => `B/. ${v.toFixed(2)}`;

// ---------------------------------------------------------------------------
// Propuesta del agente, por tipo
// ---------------------------------------------------------------------------

function Block({
	title,
	children,
}: {
	title: string;
	children: React.ReactNode;
}) {
	return (
		<section className="flex flex-col gap-2">
			<h4 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">
				{title}
			</h4>
			{children}
		</section>
	);
}

function FindingsList({ p }: { p: ParsedProposal }) {
	if (p.findings.length === 0) return null;
	return (
		<ul className="flex flex-col gap-2">
			{p.findings.map((f) => (
				<li
					key={`${f.rule}-${f.quote}`}
					className="flex flex-col gap-1 border border-danger/30 bg-danger/5 px-3 py-2 text-sm"
				>
					{f.rule ? (
						<span className="font-medium text-danger-fg">
							Regla activada: {f.rule}
						</span>
					) : null}
					{f.quote ? <span>«{f.quote}»</span> : null}
					{f.suggestion ? (
						<span className="text-muted-foreground">
							Sugerencia: {f.suggestion}
						</span>
					) : null}
				</li>
			))}
		</ul>
	);
}

function CandidateFacts({ c }: { c: Candidate }) {
	const facts = [
		c.skillCoverage != null ? `Habilidades ${pct(c.skillCoverage)}` : null,
		c.commuteMin != null ? `${c.commuteMin} min de viaje` : null,
		c.dailyCost != null ? `${money(c.dailyCost)}/día` : null,
	].filter(Boolean);
	if (facts.length === 0) return null;
	return (
		<span className="tabular font-mono text-muted-foreground text-xs">
			{facts.join(" · ")}
		</span>
	);
}

function CandidateRow({
	c,
	rank,
	children,
}: {
	c: Candidate;
	rank: number;
	children?: React.ReactNode;
}) {
	return (
		<li className="grid grid-cols-[1.75rem_1fr_auto] items-start gap-x-3 border-b py-3 last:border-b-0">
			<span
				aria-hidden="true"
				className="tabular flex size-7 items-center justify-center border font-mono text-xs"
			>
				{rank}
			</span>
			<span className="flex min-w-0 flex-col gap-0.5">
				<span className="font-medium text-sm">
					<span className="sr-only">Puesto {rank}: </span>
					{c.name}
				</span>
				{c.posting ? (
					<span className="text-muted-foreground text-sm">
						<span className="sr-only">Oferta: </span>→ {c.posting}
					</span>
				) : null}
				<CandidateFacts c={c} />
				{c.reason ? (
					<span className="text-pretty text-muted-foreground text-sm">
						{c.reason}
					</span>
				) : null}
			</span>
			<span className="flex flex-col items-end gap-1">
				{c.score != null ? (
					<span className="tabular font-mono text-sm">
						<span className="sr-only">Puntaje </span>
						{c.score.toFixed(2)}
					</span>
				) : null}
				{children}
			</span>
		</li>
	);
}

type Removal = { key: string; reason: string };

function ShortlistEditor({
	candidates,
	onChange,
}: {
	candidates: Candidate[];
	onChange: (edits: Record<string, unknown>) => void;
}) {
	const [order, setOrder] = useState(candidates.map((c) => c.key));
	const [removed, setRemoved] = useState<Removal[]>([]);
	const byKey = new Map(candidates.map((c) => [c.key, c]));
	const baseId = useId();

	function emit(nextOrder: string[], nextRemoved: Removal[]) {
		setOrder(nextOrder);
		setRemoved(nextRemoved);
		// `order` y `remove` llevan `matchResultId`; los motivos viajan aparte.
		onChange({
			order: nextOrder,
			remove: nextRemoved.map((r) => r.key),
			removals: nextRemoved.map((r) => ({
				matchResultId: r.key,
				youthId: byKey.get(r.key)?.youthId,
				reason: r.reason,
			})),
		});
	}

	function move(index: number, delta: -1 | 1) {
		const next = [...order];
		const target = index + delta;
		if (target < 0 || target >= next.length) return;
		[next[index], next[target]] = [
			next[target] as string,
			next[index] as string,
		];
		emit(next, removed);
	}

	return (
		<div className="flex flex-col gap-3">
			<ol className="flex flex-col border-y">
				{order.map((key, i) => {
					const c = byKey.get(key);
					if (!c) return null;
					return (
						<CandidateRow key={key} c={c} rank={i + 1}>
							<span className="flex gap-1">
								<Button
									type="button"
									variant="outline"
									size="icon"
									className="size-9"
									disabled={i === 0}
									aria-label={`Subir a ${c.name}`}
									onClick={() => move(i, -1)}
								>
									<ArrowUp aria-hidden="true" />
								</Button>
								<Button
									type="button"
									variant="outline"
									size="icon"
									className="size-9"
									disabled={i === order.length - 1}
									aria-label={`Bajar a ${c.name}`}
									onClick={() => move(i, 1)}
								>
									<ArrowDown aria-hidden="true" />
								</Button>
								<Button
									type="button"
									variant="outline"
									size="icon"
									className="size-9"
									aria-label={`Quitar a ${c.name}`}
									onClick={() =>
										emit(
											order.filter((k) => k !== key),
											[...removed, { key, reason: "" }],
										)
									}
								>
									<X aria-hidden="true" />
								</Button>
							</span>
						</CandidateRow>
					);
				})}
			</ol>

			{removed.length > 0 ? (
				<div className="flex flex-col gap-3 border border-dashed p-3">
					<p className="font-medium text-sm">Candidatos quitados</p>
					{removed.map((r) => {
						const c = byKey.get(r.key);
						const fieldId = `${baseId}-${r.key}`;
						return (
							<div key={r.key} className="flex flex-col gap-1.5">
								<div className="flex items-center justify-between gap-2">
									<Label htmlFor={fieldId} className="text-sm">
										Motivo para quitar a {c?.name}
									</Label>
									<Button
										type="button"
										variant="ghost"
										size="sm"
										className="h-8"
										onClick={() =>
											emit(
												[...order, r.key],
												removed.filter((x) => x.key !== r.key),
											)
										}
									>
										<Undo2 aria-hidden="true" />
										Devolver
									</Button>
								</div>
								<Input
									id={fieldId}
									value={r.reason}
									maxLength={300}
									className="h-10 text-base md:text-sm"
									onChange={(e) =>
										emit(
											order,
											removed.map((x) =>
												x.key === r.key ? { ...x, reason: e.target.value } : x,
											),
										)
									}
								/>
							</div>
						);
					})}
				</div>
			) : null}
		</div>
	);
}

function PairsTable({ pairs }: { pairs: BiasPair[] }) {
	return (
		<div className="overflow-x-auto border">
			<table className="w-full min-w-[26rem] text-sm">
				<caption className="sr-only">
					Pares contrafactuales: original y variante con puntajes
				</caption>
				<thead className="bg-muted/60 text-left text-muted-foreground">
					<tr>
						<th scope="col" className="px-3 py-2 font-medium">
							Original
						</th>
						<th scope="col" className="px-3 py-2 font-medium">
							Variante
						</th>
						<th scope="col" className="px-3 py-2 text-right font-medium">
							Resultado
						</th>
					</tr>
				</thead>
				<tbody>
					{pairs.map((p) => (
						<tr key={`${p.original}-${p.variant}`} className="border-t">
							<td className="px-3 py-2">
								{p.original}
								{p.scoreOriginal != null ? (
									<span className="tabular ml-1 font-mono text-muted-foreground">
										{p.scoreOriginal.toFixed(2)}
									</span>
								) : null}
							</td>
							<td className="px-3 py-2">
								{p.variant}
								{p.scoreVariant != null ? (
									<span className="tabular ml-1 font-mono text-muted-foreground">
										{p.scoreVariant.toFixed(2)}
									</span>
								) : null}
							</td>
							<td className="px-3 py-2 text-right">
								{p.changed == null ? null : p.changed ? (
									<span className="inline-flex items-center gap-1 font-medium text-danger-fg">
										<TriangleAlert className="size-4" aria-hidden="true" />
										Cambió
									</span>
								) : (
									<span className="inline-flex items-center gap-1 text-success-fg">
										<CircleCheck className="size-4" aria-hidden="true" />
										Sin cambio
									</span>
								)}
							</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}

const POSTING_FIELDS = [
	{ key: "title", label: "Título del puesto", type: "text" },
	{ key: "salaryMin", label: "Salario mínimo (B/.)", type: "number" },
	{ key: "salaryMax", label: "Salario máximo (B/.)", type: "number" },
	{ key: "vacancies", label: "Vacantes", type: "number" },
] as const;

type PostingField = (typeof POSTING_FIELDS)[number]["key"];

/** La API solo acepta corregir título, salario y vacantes (`edits` de `bloqueo_oferta`). */
function PostingEditor({
	p,
	onChange,
}: {
	p: ParsedProposal;
	onChange: (edits: Record<string, unknown> | null) => void;
}) {
	const baseId = useId();
	const [values, setValues] = useState<Record<PostingField, string>>({
		title: p.subject ?? "",
		salaryMin: p.salaryMin?.toString() ?? "",
		salaryMax: p.salaryMax?.toString() ?? "",
		vacancies: p.vacancies?.toString() ?? "",
	});

	function update(key: PostingField, value: string) {
		const next = { ...values, [key]: value };
		setValues(next);
		const edits: Record<string, unknown> = {};
		for (const f of POSTING_FIELDS) {
			const raw = next[f.key].trim();
			if (!raw) continue;
			edits[f.key] = f.type === "number" ? Number(raw) : raw;
		}
		onChange(Object.keys(edits).length ? edits : null);
	}

	return (
		<div className="grid gap-3 sm:grid-cols-2">
			{POSTING_FIELDS.map((f) => (
				<div key={f.key} className="flex flex-col gap-1.5">
					<Label htmlFor={`${baseId}-${f.key}`}>{f.label}</Label>
					<Input
						id={`${baseId}-${f.key}`}
						type={f.type}
						inputMode={f.type === "number" ? "decimal" : undefined}
						min={f.type === "number" ? 0 : undefined}
						value={values[f.key]}
						className="h-11 text-base md:text-sm"
						onChange={(e) => update(f.key, e.target.value)}
					/>
				</div>
			))}
		</div>
	);
}

function ProposalView({
	task,
	p,
	editing,
	onEdits,
}: {
	task: ReviewTask;
	p: ParsedProposal;
	editing: boolean;
	onEdits: (edits: Record<string, unknown> | null) => void;
}) {
	return (
		<div className="flex flex-col gap-5">
			{p.subject ? (
				<p className="text-sm">
					<span className="text-muted-foreground">Sobre: </span>
					<strong className="font-medium">{p.subject}</strong>
					{p.company ? (
						<span className="text-muted-foreground"> · {p.company}</span>
					) : null}
				</p>
			) : null}

			{task.kind === "bloqueo_oferta" ? (
				<>
					<Block title="Por qué se bloqueó">
						<FindingsList p={p} />
					</Block>
					{p.originalText ? (
						<Block title="Texto original de la empresa">
							<p className="text-pretty border bg-muted/40 px-3 py-2 text-sm">
								{p.originalText}
							</p>
						</Block>
					) : null}
					{editing ? (
						<Block title="Corrección que se publicará">
							<PostingEditor p={p} onChange={onEdits} />
						</Block>
					) : p.suggestedText ? (
						<Block title="Redacción sugerida por el agente">
							<p className="text-pretty border border-success/30 bg-success/5 px-3 py-2 text-sm">
								{p.suggestedText}
							</p>
						</Block>
					) : null}
				</>
			) : null}

			{task.kind === "lista_corta" ? (
				<Block title="Candidatos propuestos, en orden">
					{editing ? (
						<ShortlistEditor
							candidates={p.candidates}
							onChange={(e) => onEdits(e)}
						/>
					) : (
						<ol className="flex flex-col border-y">
							{p.candidates.map((c, i) => (
								<CandidateRow key={c.key} c={c} rank={i + 1} />
							))}
						</ol>
					)}
				</Block>
			) : null}

			{task.kind === "alerta_sesgo" ? (
				<>
					<Block title="Prueba contrafactual">
						<p className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm">
							{p.variable ? (
								<span>
									Variable cambiada: <strong>{p.variable}</strong>
								</span>
							) : null}
							{p.parity != null ? (
								<span className="font-medium text-danger-fg">
									Paridad{" "}
									<span className="tabular font-mono">
										{p.parity.toFixed(2)}
									</span>
									{p.threshold != null ? (
										<span className="font-normal text-muted-foreground">
											{" "}
											(umbral{" "}
											<span className="tabular font-mono">
												{p.threshold.toFixed(2)}
											</span>
											)
										</span>
									) : null}
								</span>
							) : null}
						</p>
					</Block>
					{p.pairs.length > 0 ? <PairsTable pairs={p.pairs} /> : null}
					<FindingsPlain findings={p.findings.map((f) => f.quote ?? "")} />
				</>
			) : null}

			{p.extra.length > 0 ? (
				<Block title="Otros datos de la propuesta">
					<dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
						{p.extra.map(([k, v]) => (
							<div key={k} className="contents">
								<dt className="font-mono text-muted-foreground">{k}</dt>
								<dd className="break-words">{v}</dd>
							</div>
						))}
					</dl>
				</Block>
			) : null}
		</div>
	);
}

function FindingsPlain({ findings }: { findings: string[] }) {
	const items = findings.filter(Boolean);
	if (items.length === 0) return null;
	return (
		<ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
			{items.map((f) => (
				<li key={f}>{f}</li>
			))}
		</ul>
	);
}

// ---------------------------------------------------------------------------
// Decisión
// ---------------------------------------------------------------------------

/*
 * Mismo significado que la API (apps/api/.../graph/nodes/orientador.py): «aprobar»
 * acepta la PROPUESTA del agente. En un bloqueo, la propuesta es bloquear; en una
 * alerta de sesgo, es retener la lista y volver a correr el matching.
 */
const DECISION_HELP: Record<ReviewTask["kind"], string> = {
	bloqueo_oferta:
		"Confirmar bloqueo deja la oferta sin publicar. Corregir y publicar guarda su versión (título, salario, vacantes) y la publica. Liberar oferta descarta el bloqueo y la publica tal cual; explique el motivo en el comentario.",
	lista_corta:
		"Enviar lista la manda a la empresa y agenda las entrevistas sin choques. Reordenar o quitar le deja cambiar el orden o sacar candidatos con motivo antes de enviarla. Descartar lista no envía a nadie; explique el motivo.",
	alerta_sesgo:
		"Aceptar hallazgo retiene la lista corta de esta corrida: hay que volver a ejecutar el matching. Descartar alerta deja seguir la lista; la justificación es obligatoria.",
};

const DECISION_LABEL: Record<
	ReviewTask["kind"],
	Record<ReviewDecision["decision"], string>
> = {
	bloqueo_oferta: {
		aprobar: "Confirmar bloqueo",
		editar: "Corregir y publicar",
		rechazar: "Liberar oferta",
	},
	lista_corta: {
		aprobar: "Enviar lista",
		editar: "Reordenar o quitar",
		rechazar: "Descartar lista",
	},
	alerta_sesgo: {
		aprobar: "Aceptar hallazgo",
		editar: "Editar",
		rechazar: "Descartar alerta",
	},
};

function DecisionForm({
	task,
	simulated,
	edits,
	editing,
	setEditing,
	onDecided,
}: {
	task: ReviewTask;
	simulated: boolean;
	edits: Record<string, unknown> | null;
	editing: boolean;
	setEditing: (v: boolean) => void;
	onDecided: (resolved: ReviewTask) => void;
}) {
	const ids = { reviewer: useId(), comment: useId(), help: useId() };
	const [reviewer, setReviewer] = useState("");
	const [comment, setComment] = useState("");
	const [pending, setPending] = useState<ReviewDecision["decision"] | null>(
		null,
	);
	const [error, setError] = useState<string | null>(null);
	const canEdit = task.kind !== "alerta_sesgo";

	useEffect(() => {
		setReviewer(recallReviewer());
	}, []);

	async function submit(decision: ReviewDecision["decision"]) {
		setError(null);
		if (!reviewer.trim()) {
			setError("Escriba su nombre: queda registrado junto a la decisión.");
			document.getElementById(ids.reviewer)?.focus();
			return;
		}
		if (decision === "rechazar" && !comment.trim()) {
			setError(
				`Para «${DECISION_LABEL[task.kind].rechazar}», explique el motivo en el comentario.`,
			);
			document.getElementById(ids.comment)?.focus();
			return;
		}
		if (decision === "editar" && !edits) {
			setError("Haga al menos un cambio antes de guardar la edición.");
			return;
		}
		if (
			decision === "editar" &&
			Array.isArray((edits as { removals?: Removal[] } | null)?.removals) &&
			(edits as { removals: { reason: string }[] }).removals.some(
				(r) => !r.reason.trim(),
			)
		) {
			setError("Indique el motivo de cada candidato que quitó.");
			return;
		}

		setPending(decision);
		rememberReviewer(reviewer.trim());
		const body: ReviewDecision = {
			decision,
			reviewer: reviewer.trim(),
			comment: comment.trim() || undefined,
			edits: decision === "editar" ? (edits ?? undefined) : undefined,
		};
		const r = await decideReview(task.id, body, { simulated });
		setPending(null);
		if (!r.ok) {
			setError(r.message);
			return;
		}
		const status: ReviewStatus =
			decision === "aprobar"
				? "aprobada"
				: decision === "editar"
					? "editada"
					: "rechazada";
		toast.success(
			decision === "rechazar"
				? "Decisión registrada: rechazada."
				: "Decisión registrada. El flujo continúa.",
			{
				description: simulated
					? "Datos de ejemplo: no se reanudó ningún flujo real."
					: undefined,
			},
		);
		onDecided({
			...task,
			status,
			reviewer: body.reviewer,
			comment: body.comment,
			resolvedAt: new Date().toISOString(),
		});
	}

	const busy = pending != null;

	return (
		<form
			onSubmit={(e) => e.preventDefault()}
			className="flex flex-col gap-4 border-t pt-5"
			aria-labelledby={`${ids.help}-t`}
		>
			<div className="flex flex-col gap-1">
				<h3 id={`${ids.help}-t`} className="font-semibold text-base">
					Su decisión
				</h3>
				<p id={ids.help} className="text-muted-foreground text-sm">
					{DECISION_HELP[task.kind]}
				</p>
			</div>

			<div className="grid gap-4 sm:grid-cols-[14rem_1fr]">
				<div className="flex flex-col gap-1.5">
					<Label htmlFor={ids.reviewer} className="font-medium text-sm">
						Su nombre
					</Label>
					<Input
						id={ids.reviewer}
						value={reviewer}
						autoComplete="name"
						maxLength={120}
						disabled={busy}
						onChange={(e) => setReviewer(e.target.value)}
						className="h-10 text-base md:text-sm"
					/>
				</div>
				<div className="flex flex-col gap-1.5">
					<Label htmlFor={ids.comment} className="font-medium text-sm">
						Comentario{" "}
						<span className="font-normal text-muted-foreground">
							(obligatorio para «{DECISION_LABEL[task.kind].rechazar}»)
						</span>
					</Label>
					<Textarea
						id={ids.comment}
						value={comment}
						maxLength={2000}
						disabled={busy}
						onChange={(e) => setComment(e.target.value)}
						className="min-h-20 text-base md:text-sm"
					/>
				</div>
			</div>

			{error ? (
				<p
					role="alert"
					className="flex items-start gap-1.5 text-danger-fg text-sm"
				>
					<TriangleAlert
						className="mt-0.5 size-4 shrink-0"
						aria-hidden="true"
					/>
					{error}
				</p>
			) : null}

			<div className="flex flex-wrap gap-2">
				<Button
					type="button"
					size="lg"
					className="h-11 px-5 text-sm"
					disabled={busy || editing}
					onClick={() => submit("aprobar")}
				>
					<CircleCheck aria-hidden="true" />
					{pending === "aprobar"
						? "Registrando…"
						: DECISION_LABEL[task.kind].aprobar}
				</Button>
				{canEdit ? (
					editing ? (
						<>
							<Button
								type="button"
								size="lg"
								className="h-11 px-5 text-sm"
								disabled={busy}
								onClick={() => submit("editar")}
							>
								<Pencil aria-hidden="true" />
								{pending === "editar" ? "Registrando…" : "Guardar edición"}
							</Button>
							<Button
								type="button"
								variant="outline"
								size="lg"
								className="h-11 px-5 text-sm"
								disabled={busy}
								onClick={() => setEditing(false)}
							>
								Cancelar edición
							</Button>
						</>
					) : (
						<Button
							type="button"
							variant="outline"
							size="lg"
							className="h-11 px-5 text-sm"
							disabled={busy}
							onClick={() => setEditing(true)}
						>
							<Pencil aria-hidden="true" />
							{DECISION_LABEL[task.kind].editar}
						</Button>
					)
				) : null}
				<Button
					type="button"
					variant="outline"
					size="lg"
					className="h-11 border-danger/50 px-5 text-danger-fg text-sm hover:bg-danger/10"
					disabled={busy || editing}
					onClick={() => submit("rechazar")}
				>
					<Ban aria-hidden="true" />
					{pending === "rechazar"
						? "Registrando…"
						: DECISION_LABEL[task.kind].rechazar}
				</Button>
			</div>
		</form>
	);
}

// ---------------------------------------------------------------------------
// Panel de detalle
// ---------------------------------------------------------------------------

export function ReviewDetail({
	task,
	simulated,
	onDecided,
	headingRef,
}: {
	task: ReviewTask;
	simulated: boolean;
	onDecided: (resolved: ReviewTask) => void;
	headingRef: React.Ref<HTMLHeadingElement>;
}) {
	const proposal = parseProposal(task);
	const [editing, setEditing] = useState(false);
	const [edits, setEdits] = useState<Record<string, unknown> | null>(null);
	const [trace, setTrace] = useState<
		{ status: "loading" } | { status: "ready"; steps: AgentTrace[] | null }
	>({ status: "loading" });

	useEffect(() => {
		let live = true;
		setTrace({ status: "loading" });
		loadReviewTrace(task.threadId, simulated).then((steps) => {
			if (live) setTrace({ status: "ready", steps });
		});
		return () => {
			live = false;
		};
	}, [task.threadId, simulated]);

	const agent = task.agent as AgentTrace["agent"] | undefined;
	const pending = task.status === "pendiente";

	return (
		<article
			aria-labelledby="detalle-titulo"
			className="flex flex-col gap-6 border p-4 sm:p-5"
		>
			<header className="flex flex-col gap-2">
				<div className="flex flex-wrap items-center justify-between gap-2">
					<p className="flex flex-wrap items-center gap-2 text-sm">
						{agent ? <AgentBadge agent={agent} /> : null}
						<span className="text-muted-foreground">
							{agent ? "propone" : "Propuesta del sistema"} ·{" "}
							{timeAgo(task.createdAt)}
						</span>
					</p>
					<ReviewStatusBadge status={task.status} />
				</div>
				<h2
					id="detalle-titulo"
					ref={headingRef}
					tabIndex={-1}
					className="text-balance font-semibold text-xl outline-none"
				>
					{kindMeta[task.kind].label}
					{proposal.subject ? `: ${proposal.subject}` : ""}
				</h2>
			</header>

			<section
				aria-labelledby="explicacion"
				className="flex flex-col gap-1.5 border-primary border-l-2 bg-muted/40 px-4 py-3"
			>
				<h3
					id="explicacion"
					className="font-medium text-muted-foreground text-xs uppercase tracking-wide"
				>
					Por qué lo propone
				</h3>
				<p className="text-pretty text-sm leading-relaxed">
					{task.explanation}
				</p>
			</section>

			<ProposalView
				key={task.id}
				task={task}
				p={proposal}
				editing={editing}
				onEdits={setEdits}
			/>

			{trace.status === "loading" ? (
				<div className="flex flex-col gap-2">
					<output aria-live="polite" className="sr-only">
						Cargando la traza…
					</output>
					<Skeleton className="h-5 w-1/3" />
					<Skeleton className="h-14 w-full" />
				</div>
			) : trace.steps && trace.steps.length > 0 ? (
				<div className="flex flex-col gap-1">
					<TraceSteps steps={trace.steps} title="Traza del flujo" />
					<TraceLink threadId={task.threadId} className="self-start">
						Ver la traza completa con herramientas y tiempos
					</TraceLink>
				</div>
			) : (
				<p className="text-muted-foreground text-sm">
					La traza de este flujo aún no está disponible. Hilo:{" "}
					<span className="font-mono">{task.threadId}</span>
				</p>
			)}

			{pending ? (
				<DecisionForm
					task={task}
					simulated={simulated}
					edits={edits}
					editing={editing}
					setEditing={(v) => {
						setEditing(v);
						if (!v) setEdits(null);
					}}
					onDecided={onDecided}
				/>
			) : (
				<section
					aria-labelledby="resolucion"
					className="flex flex-col gap-1.5 border-t pt-5 text-sm"
				>
					<h3 id="resolucion" className="font-semibold text-base">
						Decisión registrada
					</h3>
					<p>
						<ReviewStatusBadge status={task.status} />
						{task.reviewer ? <span> por {task.reviewer}</span> : null}
						{task.resolvedAt ? (
							<span className="text-muted-foreground">
								{" "}
								· {timeAgo(task.resolvedAt)}
							</span>
						) : null}
					</p>
					{task.comment ? (
						<p className="text-pretty text-muted-foreground">
							«{task.comment}»
						</p>
					) : null}
					{task.kind === "lista_corta" &&
					task.status !== "rechazada" &&
					!simulated ? (
						<ScheduledInterviews task={task} />
					) : null}
				</section>
			)}
		</article>
	);
}
