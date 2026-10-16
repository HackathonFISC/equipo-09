"use client";

import { Button } from "@puente/ui/components/button";
import { Label } from "@puente/ui/components/label";
import { Textarea } from "@puente/ui/components/textarea";
import {
	ClipboardPaste,
	ScanText,
	Sparkles,
	TriangleAlert,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { AgentWorking, TraceSteps } from "@/components/agents";
import { DataSourceNote } from "@/components/data-states";
import { PostingList } from "@/components/posting-list";
import {
	type IngestOutcome,
	ingestPosting,
	type Result,
} from "@/lib/api/agents";

const MAX = 20_000;
const MIN = 40;

const SAMPLE = `Se busca cajera para minisúper en Juan Díaz.
Buena presencia, entre 18 y 25 años.
Funciones: atender clientes, cobrar en caja y reponer mercancía en los anaqueles.
Deseable Excel básico.
Horario de lunes a viernes de 8:00 a 4:00 p.m. Salario B/. 650. 2 vacantes.`;

type State =
	| { status: "idle" }
	| { status: "working" }
	| { status: "done"; result: Result<IngestOutcome> };

export function PostingIngest({ companyId }: { companyId: string }) {
	const router = useRouter();
	const [text, setText] = useState("");
	const [touched, setTouched] = useState(false);
	const [state, setState] = useState<State>({ status: "idle" });
	const resultRef = useRef<HTMLHeadingElement>(null);
	const ids = { text: useId(), hint: useId(), error: useId() };

	const trimmed = text.trim();
	const invalid =
		trimmed.length < MIN
			? "Pega al menos un par de frases: el puesto, las funciones y el horario."
			: null;
	const showInvalid = touched && invalid;

	useEffect(() => {
		if (state.status === "done") resultRef.current?.focus();
	}, [state.status]);

	async function onSubmit(e: React.FormEvent) {
		e.preventDefault();
		setTouched(true);
		if (invalid) return;
		setState({ status: "working" });
		const result = await ingestPosting({ companyId, text: trimmed });
		setState({ status: "done", result });
		if (result.ok && result.source === "api") router.refresh();
	}

	const working = state.status === "working";

	return (
		<section
			id="nueva-oferta"
			aria-labelledby="nueva-oferta-titulo"
			className="grid scroll-mt-20 gap-6 border p-4 sm:p-6 lg:grid-cols-2"
		>
			<form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
				<div className="flex flex-col gap-1">
					<h2 id="nueva-oferta-titulo" className="font-semibold text-lg">
						Nueva oferta
					</h2>
					<p className="text-muted-foreground text-sm">
						Pega el anuncio tal como lo tienes. Mercado lo convierte en
						requisitos medibles y el Auditor lo revisa antes de publicarlo.
					</p>
				</div>

				<div className="flex flex-col gap-2">
					<div className="flex flex-wrap items-center justify-between gap-2">
						<Label htmlFor={ids.text} className="font-medium text-sm">
							Texto de la oferta
						</Label>
						<Button
							type="button"
							variant="ghost"
							size="sm"
							className="h-9"
							onClick={() => {
								setText(SAMPLE);
								setTouched(false);
							}}
							disabled={working}
						>
							<ClipboardPaste aria-hidden="true" />
							Usar oferta de ejemplo
						</Button>
					</div>
					<Textarea
						id={ids.text}
						value={text}
						onChange={(e) => setText(e.target.value)}
						onBlur={() => setTouched(true)}
						maxLength={MAX}
						disabled={working}
						aria-invalid={showInvalid ? true : undefined}
						aria-describedby={`${ids.hint}${showInvalid ? ` ${ids.error}` : ""}`}
						placeholder="Ej.: Se busca auxiliar de bodega en Tocumen. Funciones: recibir y despachar mercancía…"
						className="min-h-56 text-base md:text-sm"
					/>
					<p
						id={ids.hint}
						className="flex justify-between gap-3 text-muted-foreground text-xs"
					>
						<span>Puesto, funciones, ubicación, horario y salario.</span>
						<span className="tabular font-mono">
							{text.length.toLocaleString("es-PA")}/
							{MAX.toLocaleString("es-PA")}
						</span>
					</p>
					{showInvalid ? (
						<p
							id={ids.error}
							className="flex items-start gap-1.5 text-danger-fg text-sm"
						>
							<TriangleAlert
								className="mt-0.5 size-4 shrink-0"
								aria-hidden="true"
							/>
							{invalid}
						</p>
					) : null}
				</div>

				<Button
					type="submit"
					size="lg"
					className="h-11 text-sm"
					disabled={working}
				>
					<ScanText aria-hidden="true" />
					{working ? "Procesando…" : "Estructurar oferta"}
				</Button>
			</form>

			<div className="flex flex-col gap-4 lg:border-l lg:pl-6">
				{state.status === "idle" ? (
					<div className="flex h-full flex-col items-center justify-center gap-2 border border-dashed px-6 py-12 text-center">
						<Sparkles
							className="size-6 text-muted-foreground"
							aria-hidden="true"
						/>
						<p className="font-medium">Aquí verás lo que entendió Mercado</p>
						<p className="max-w-xs text-muted-foreground text-sm">
							Habilidades normalizadas, requisitos obligatorios y deseables,
							ubicación y la revisión del Auditor, con su explicación.
						</p>
					</div>
				) : null}

				{working ? (
					<div className="flex flex-col gap-2">
						<AgentWorking agent="mercado">
							<strong className="font-medium">Mercado</strong> está extrayendo
							los requisitos de tu oferta…
						</AgentWorking>
						<AgentWorking agent="auditor">
							Luego el <strong className="font-medium">Auditor</strong> revisa
							que no haya requisitos discriminatorios.
						</AgentWorking>
					</div>
				) : null}

				{state.status === "done" ? (
					<IngestResult result={state.result} headingRef={resultRef} />
				) : null}
			</div>
		</section>
	);
}

function IngestResult({
	result,
	headingRef,
}: {
	result: Result<IngestOutcome>;
	headingRef: React.RefObject<HTMLHeadingElement | null>;
}) {
	if (!result.ok) {
		return (
			<div
				role="alert"
				className="flex flex-col gap-2 border border-danger/40 bg-danger/5 p-4"
			>
				<h3
					ref={headingRef}
					tabIndex={-1}
					className="flex items-center gap-2 font-medium text-danger-fg outline-none"
				>
					<TriangleAlert className="size-5 shrink-0" aria-hidden="true" />
					{result.problem?.guardrail
						? "Oferta detenida por un guardrail"
						: "No pudimos procesar la oferta"}
				</h3>
				<p className="text-sm">{result.message}</p>
			</div>
		);
	}

	const { posting, trace } = result.data;
	const missing = [
		posting.location ? null : "ubicación",
		posting.salaryMin != null || posting.salaryMax != null ? null : "salario",
		posting.schedule?.length ? null : "horario",
	].filter((m): m is string => m !== null);

	return (
		<div className="flex flex-col gap-4">
			<div className="flex flex-col gap-2">
				<h3
					ref={headingRef}
					tabIndex={-1}
					className="font-medium text-muted-foreground text-sm outline-none"
				>
					Oferta estructurada
				</h3>
				<DataSourceNote source={result.source} reason={result.reason} />
			</div>

			<PostingList postings={[posting]} />

			{posting.requirements.length === 0 ? (
				<p className="border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning-fg">
					Mercado no encontró habilidades concretas. Describe las tareas del
					puesto («atender clientes», «cobrar en caja») para que podamos
					emparejar candidatos.
				</p>
			) : null}

			{missing.length > 0 ? (
				<p className="text-muted-foreground text-sm">
					No se indicó: {missing.join(", ")}. Sin esos datos el matching no
					puede calcular traslado ni compatibilidad salarial.
				</p>
			) : null}

			{trace && trace.length > 0 ? (
				<TraceSteps steps={trace} />
			) : (
				<p className="text-muted-foreground text-sm">
					La traza de esta oferta todavía no está disponible.
				</p>
			)}
		</div>
	);
}
