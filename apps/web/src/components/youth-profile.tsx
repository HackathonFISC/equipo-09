"use client";

import { Button, buttonVariants } from "@puente/ui/components/button";
import { Label } from "@puente/ui/components/label";
import { Skeleton } from "@puente/ui/components/skeleton";
import { Textarea } from "@puente/ui/components/textarea";
import { cn } from "@puente/ui/lib/utils";
import {
	Briefcase,
	CircleCheck,
	FileUp,
	GraduationCap,
	MessagesSquare,
	RotateCw,
	TriangleAlert,
	UserRoundSearch,
} from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { AgentWorking, TraceSteps } from "@/components/agents";
import { DataSourceNote } from "@/components/data-states";
import { ProfileSkills } from "@/components/profile-skills";
import {
	answerInterview,
	type CvOutcome,
	getYouth,
	mergeProfileSkills,
	type Result,
	uploadCv,
} from "@/lib/api/agents";
import type { InterviewStep, ProfileSkill, Youth } from "@/lib/api/client";
import { plural } from "@/lib/format";
import { rememberYouth } from "@/lib/youth-session";

const MAX_QUESTIONS = 5;
const MAX_FILE = 5 * 1024 * 1024;

type Loaded = Extract<Result<Youth>, { ok: true }> & { status: "ready" };

function ErrorBox({ title, message }: { title: string; message: string }) {
	return (
		<div
			role="alert"
			className="flex flex-col gap-1 border border-danger/40 bg-danger/5 p-4 text-sm"
		>
			<p className="flex items-center gap-2 font-medium text-danger-fg">
				<TriangleAlert className="size-4 shrink-0" aria-hidden="true" />
				{title}
			</p>
			<p>{message}</p>
		</div>
	);
}

export function YouthProfile({ youthId }: { youthId: string }) {
	const [state, setState] = useState<
		{ status: "loading" } | { status: "error"; message: string } | Loaded
	>({ status: "loading" });
	const [fresh, setFresh] = useState<Set<string>>(new Set());

	const load = useCallback(async () => {
		setState({ status: "loading" });
		const r = await getYouth(youthId);
		if (r.ok) rememberYouth(youthId);
		setState(
			r.ok
				? { ...r, status: "ready" }
				: { status: "error", message: r.message },
		);
	}, [youthId]);

	useEffect(() => {
		void load();
	}, [load]);

	/** Fusiona habilidades nuevas y las marca como recién descubiertas. */
	const addSkills = useCallback((skills: ProfileSkill[], youth?: Youth) => {
		setState((prev) => {
			if (prev.status !== "ready") return prev;
			const known = new Set(prev.data.skills.map((s) => s.skill.id));
			const added = skills.filter((s) => !known.has(s.skill.id));
			if (added.length)
				setFresh((f) => new Set([...f, ...added.map((s) => s.skill.id)]));
			const base = youth ?? prev.data;
			return {
				...prev,
				data: {
					...base,
					skills: mergeProfileSkills(prev.data.skills, [
						...(youth?.skills ?? []),
						...skills,
					]),
				},
			};
		});
	}, []);

	if (state.status === "loading") {
		return (
			<div className="flex flex-col gap-4">
				<output aria-live="polite" className="sr-only">
					Cargando tu perfil…
				</output>
				<Skeleton className="h-8 w-2/3" />
				<Skeleton className="h-24 w-full" />
				<Skeleton className="h-24 w-full" />
			</div>
		);
	}

	if (state.status === "error") {
		return (
			<div className="flex flex-col items-start gap-3">
				<ErrorBox title="No pudimos cargar tu perfil" message={state.message} />
				<Button variant="outline" size="lg" className="h-11" onClick={load}>
					<RotateCw aria-hidden="true" />
					Reintentar
				</Button>
			</div>
		);
	}

	const youth = state.data;
	const hasSkills = youth.skills.length > 0;

	return (
		<div className="flex flex-col gap-10">
			<section aria-labelledby="habilidades" className="flex flex-col gap-4">
				<div className="flex flex-col gap-2">
					<h2 id="habilidades" className="font-semibold text-xl">
						Hola, {youth.displayName}
					</h2>
					<p className="text-muted-foreground text-sm">
						{hasSkills
							? `El agente de Perfil encontró ${plural(youth.skills.length, "habilidad", "habilidades")}. Cada una lleva la frase que la respalda.`
							: "Todavía no conocemos tus habilidades. Sube tu CV o responde la entrevista: con cualquiera de las dos basta."}
					</p>
					<DataSourceNote source={state.source} reason={state.reason} />
				</div>
				{hasSkills ? (
					<Link
						href={`/joven/oportunidades?id=${youthId}` as Route}
						className={cn(
							buttonVariants({ size: "lg" }),
							"h-12 w-full text-base",
						)}
					>
						<Briefcase aria-hidden="true" />
						Ver mis oportunidades
					</Link>
				) : null}
				{hasSkills ? (
					<Link
						href={`/joven/formacion?id=${youthId}` as Route}
						className={cn(
							buttonVariants({ variant: "outline", size: "lg" }),
							"h-12 w-full text-base",
						)}
					>
						<GraduationCap aria-hidden="true" />
						Ver mi ruta de formación
					</Link>
				) : null}
				{hasSkills ? (
					<ProfileSkills skills={youth.skills} highlight={fresh} />
				) : (
					<div className="flex flex-col items-center gap-2 border border-dashed px-6 py-10 text-center">
						<UserRoundSearch
							className="size-7 text-agent-perfil"
							aria-hidden="true"
						/>
						<p className="font-medium">Tu perfil está vacío</p>
						<p className="max-w-xs text-muted-foreground text-sm">
							Lo que hayas hecho en casa, en un negocio familiar o en trabajos
							informales también cuenta.
						</p>
					</div>
				)}
			</section>

			<CvUpload
				youthId={youthId}
				onDone={(out) => addSkills(out.youth.skills, out.youth)}
			/>

			<Interview
				youthId={youthId}
				shortVersion={hasSkills}
				onSkills={(skills) => addSkills(skills)}
				onFinished={async () => {
					const r = await getYouth(youthId);
					if (r.ok) addSkills(r.data.skills, r.data);
				}}
			/>
		</div>
	);
}

// ---------------------------------------------------------------------------
// CV
// ---------------------------------------------------------------------------

function CvUpload({
	youthId,
	onDone,
}: {
	youthId: string;
	onDone: (out: CvOutcome) => void;
}) {
	const ids = { file: useId(), text: useId(), hint: useId() };
	const [file, setFile] = useState<File | null>(null);
	const [text, setText] = useState("");
	const [error, setError] = useState<string | null>(null);
	const [pending, setPending] = useState(false);
	const [result, setResult] = useState<Result<CvOutcome> | null>(null);

	function pickFile(f: File | null) {
		setError(null);
		if (f && f.size > MAX_FILE) {
			setFile(null);
			setError("El archivo pesa más de 5 MB. Prueba con uno más liviano.");
			return;
		}
		setFile(f);
	}

	async function onSubmit(e: React.FormEvent) {
		e.preventDefault();
		setError(null);
		if (!file && !text.trim()) {
			setError("Elige un archivo o pega el texto de tu CV.");
			return;
		}
		setPending(true);
		setResult(null);
		// Un .txt se envía como texto: el contrato acepta archivos PDF o imagen.
		const isText =
			file && (file.type === "text/plain" || /\.txt$/i.test(file.name));
		const input = isText
			? { text: (await file.text()).slice(0, 20_000) }
			: { file: file ?? undefined, text: text.trim() || undefined };
		const r = await uploadCv(youthId, input);
		setPending(false);
		setResult(r);
		if (r.ok) onDone(r.data);
	}

	return (
		<section
			aria-labelledby="cv"
			className="flex flex-col gap-4 border p-4 sm:p-5"
		>
			<div className="flex flex-col gap-1">
				<h2 id="cv" className="flex items-center gap-2 font-semibold text-lg">
					<FileUp className="size-5 text-agent-perfil" aria-hidden="true" />
					¿Tienes CV?
				</h2>
				<p className="text-muted-foreground text-sm">
					Súbelo en PDF o texto, o pega su contenido. Perfil lo lee y anota de
					dónde sale cada habilidad.
				</p>
			</div>

			<form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
				<div className="flex flex-col gap-2">
					<Label htmlFor={ids.file} className="font-medium text-sm">
						Archivo
					</Label>
					<input
						id={ids.file}
						type="file"
						accept="application/pdf,.pdf,text/plain,.txt"
						disabled={pending}
						aria-describedby={ids.hint}
						onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
						className="min-h-11 w-full border border-input p-2 text-sm file:mr-3 file:h-8 file:border file:border-input file:bg-muted file:px-3 file:font-medium file:text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
					/>
					<p id={ids.hint} className="text-muted-foreground text-xs">
						PDF o .txt, máximo 5 MB.
					</p>
				</div>
				<div className="flex flex-col gap-2">
					<Label htmlFor={ids.text} className="font-medium text-sm">
						O pega el texto
					</Label>
					<Textarea
						id={ids.text}
						value={text}
						onChange={(e) => setText(e.target.value)}
						maxLength={20_000}
						disabled={pending || Boolean(file)}
						placeholder="Ej.: Trabajé en el minisúper de mi tío atendiendo clientes y cobrando en caja."
						className="min-h-28 text-base md:text-sm"
					/>
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
				<Button
					type="submit"
					size="lg"
					className="h-11 text-sm"
					disabled={pending}
				>
					{pending ? "Leyendo tu CV…" : "Analizar CV"}
				</Button>
			</form>

			{pending ? (
				<AgentWorking agent="perfil">
					<strong className="font-medium">Perfil</strong> está leyendo tu CV y
					buscando evidencia de cada habilidad…
				</AgentWorking>
			) : null}

			{result && !result.ok ? (
				<ErrorBox
					title={
						result.problem?.guardrail
							? "Tu CV fue detenido por un guardrail"
							: "No pudimos leer tu CV"
					}
					message={result.message}
				/>
			) : null}

			{result?.ok ? (
				<div className="flex flex-col gap-3">
					<p className="flex items-center gap-2 font-medium text-sm text-success-fg">
						<CircleCheck className="size-4" aria-hidden="true" />
						CV analizado. Tus habilidades se actualizaron arriba.
					</p>
					{result.source === "mock" ? (
						<DataSourceNote source="mock" reason={result.reason} />
					) : null}
					{result.data.trace?.length ? (
						<TraceSteps steps={result.data.trace} />
					) : null}
				</div>
			) : null}
		</section>
	);
}

// ---------------------------------------------------------------------------
// Entrevista
// ---------------------------------------------------------------------------

type InterviewState =
	| { status: "idle" }
	| { status: "asking"; step: InterviewStep; number: number }
	| { status: "done"; total: number };

function Interview({
	youthId,
	shortVersion,
	onSkills,
	onFinished,
}: {
	youthId: string;
	shortVersion: boolean;
	onSkills: (skills: ProfileSkill[]) => void;
	onFinished: () => void | Promise<void>;
}) {
	const answerId = useId();
	const questionId = useId();
	const [state, setState] = useState<InterviewState>({ status: "idle" });
	// El título no cambia a mitad de entrevista aunque aparezcan habilidades.
	const [startedShort] = useState(shortVersion);
	const [answer, setAnswer] = useState("");
	const [pending, setPending] = useState(false);
	const [error, setError] = useState<Extract<
		Result<unknown>,
		{ ok: false }
	> | null>(null);
	const [source, setSource] = useState<{ mock: boolean; reason?: string }>({
		mock: false,
	});
	const answerRef = useRef<HTMLTextAreaElement>(null);

	const asking = state.status === "asking" ? state : null;
	useEffect(() => {
		if (asking) answerRef.current?.focus();
	}, [asking]);

	async function send(value: string | null) {
		setPending(true);
		setError(null);
		const r = await answerInterview(youthId, value);
		setPending(false);
		if (!r.ok) {
			setError(r);
			return;
		}
		setSource({ mock: r.source === "mock", reason: r.reason });
		if (r.data.discoveredSkills?.length) onSkills(r.data.discoveredSkills);
		const number = value == null ? 1 : (asking?.number ?? 0) + 1;
		if (r.data.done || !r.data.question) {
			setState({ status: "done", total: number - 1 });
			await onFinished();
		} else {
			setState({ status: "asking", step: r.data, number });
		}
		setAnswer("");
	}

	return (
		<section
			aria-labelledby="entrevista"
			className="flex flex-col gap-4 border p-4 sm:p-5"
		>
			<div className="flex flex-col gap-1">
				<h2
					id="entrevista"
					className="flex items-center gap-2 font-semibold text-lg"
				>
					<MessagesSquare
						className="size-5 text-agent-perfil"
						aria-hidden="true"
					/>
					{startedShort ? "Completa tu perfil" : "¿No tienes CV?"}
				</h2>
				<p className="text-muted-foreground text-sm">
					Responde hasta {MAX_QUESTIONS} preguntas cortas con tus palabras. No
					hay respuestas malas: cada habilidad que encontremos queda con tu
					frase como evidencia.
				</p>
			</div>

			{state.status === "idle" ? (
				<Button
					size="lg"
					className="h-11 text-sm"
					disabled={pending}
					onClick={() => send(null)}
				>
					{pending ? "Preparando la primera pregunta…" : "Empezar entrevista"}
				</Button>
			) : null}

			{asking ? (
				<form
					onSubmit={(e) => {
						e.preventDefault();
						if (answer.trim()) void send(answer.trim());
					}}
					className="flex flex-col gap-4"
				>
					<div className="flex flex-col gap-2">
						<div className="flex items-center justify-between gap-3 text-muted-foreground text-xs">
							<span>
								Pregunta{" "}
								<span className="tabular font-mono">{asking.number}</span> de
								hasta <span className="tabular font-mono">{MAX_QUESTIONS}</span>
							</span>
						</div>
						<progress
							max={MAX_QUESTIONS}
							value={asking.number - 1}
							aria-label="Avance de la entrevista"
							className="h-1.5 w-full appearance-none overflow-hidden bg-muted [&::-moz-progress-bar]:bg-agent-perfil [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:bg-agent-perfil"
						/>
					</div>
					<p
						id={questionId}
						aria-live="polite"
						className="text-pretty font-medium text-lg"
					>
						{asking.step.question}
					</p>
					<div className="flex flex-col gap-2">
						<Label htmlFor={answerId} className="font-medium text-sm">
							Tu respuesta
						</Label>
						<Textarea
							ref={answerRef}
							id={answerId}
							aria-describedby={questionId}
							value={answer}
							onChange={(e) => setAnswer(e.target.value)}
							maxLength={2000}
							disabled={pending}
							className="min-h-28 text-base md:text-sm"
							onKeyDown={(e) => {
								if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
									e.currentTarget.form?.requestSubmit();
								}
							}}
						/>
					</div>
					<div className="flex flex-col gap-2 sm:flex-row">
						<Button
							type="submit"
							size="lg"
							className="h-11 flex-1 text-sm"
							disabled={pending || !answer.trim()}
						>
							{pending ? "Perfil está pensando…" : "Enviar respuesta"}
						</Button>
						<Button
							type="button"
							variant="outline"
							size="lg"
							className="h-11 text-sm"
							disabled={pending}
							onClick={() => send("No tengo experiencia con eso.")}
						>
							No sé / saltar
						</Button>
					</div>
				</form>
			) : null}

			{pending && asking ? (
				<AgentWorking agent="perfil">
					<strong className="font-medium">Perfil</strong> busca habilidades en
					tu respuesta…
				</AgentWorking>
			) : null}

			{error ? (
				<ErrorBox
					title={
						error.problem?.guardrail
							? "Respuesta detenida por un guardrail"
							: "No pudimos continuar la entrevista"
					}
					message={error.message}
				/>
			) : null}

			{state.status === "done" ? (
				<p className="flex items-center gap-2 border border-success/40 bg-success/5 p-4 font-medium text-sm">
					<CircleCheck className="size-4 text-success-fg" aria-hidden="true" />
					Entrevista terminada: respondiste{" "}
					{plural(state.total, "pregunta", "preguntas")}. Tu perfil ya está
					actualizado arriba.
				</p>
			) : null}

			{source.mock && state.status !== "idle" ? (
				<DataSourceNote source="mock" reason={source.reason} />
			) : null}
		</section>
	);
}
