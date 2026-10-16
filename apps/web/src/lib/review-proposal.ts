/**
 * `ReviewTask.proposal` es un objeto libre en el contrato. Estas funciones lo
 * leen de forma defensiva: lo que reconocemos se muestra con formato y el
 * resto cae a una lista genérica, así un cambio de forma en la API no rompe
 * la bandeja.
 */
import type { ReviewKind, ReviewTask } from "@/lib/api/client";

type Rec = Record<string, unknown>;

const isRec = (v: unknown): v is Rec =>
	typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown) => (typeof v === "string" && v.trim() ? v : undefined);
const num = (v: unknown) =>
	typeof v === "number" && Number.isFinite(v) ? v : undefined;

export type Finding = { rule?: string; quote?: string; suggestion?: string };

export type Candidate = {
	/** Clave estable para reordenar y quitar. */
	key: string;
	youthId?: string;
	name: string;
	score?: number;
	commuteMin?: number;
	dailyCost?: number;
	skillCoverage?: number;
	reason?: string;
};

export type BiasPair = {
	original: string;
	variant: string;
	scoreOriginal?: number;
	scoreVariant?: number;
	changed?: boolean;
};

export type ParsedProposal = {
	subject?: string;
	company?: string;
	vacancies?: number;
	findings: Finding[];
	originalText?: string;
	suggestedText?: string;
	candidates: Candidate[];
	variable?: string;
	parity?: number;
	threshold?: number;
	pairs: BiasPair[];
	/** Claves que no reconocemos, para no esconder información de la propuesta. */
	extra: [key: string, value: string][];
};

const KNOWN = new Set([
	"postingTitle",
	"title",
	"company",
	"vacancies",
	"findings",
	"originalText",
	"suggestedText",
	"candidates",
	"variable",
	"parity",
	"threshold",
	"pairs",
]);

function parseFindings(raw: unknown): Finding[] {
	if (!Array.isArray(raw)) return [];
	return raw.flatMap((f): Finding[] => {
		if (typeof f === "string") return [{ quote: f }];
		if (isRec(f)) {
			return [
				{
					rule: str(f.rule),
					quote: str(f.quote) ?? str(f.text),
					suggestion: str(f.suggestion),
				},
			];
		}
		return [];
	});
}

function parseCandidates(raw: unknown): Candidate[] {
	if (!Array.isArray(raw)) return [];
	return raw.flatMap((c, i): Candidate[] => {
		if (!isRec(c)) return [];
		const youthId = str(c.youthId);
		return [
			{
				key: youthId ?? `c${i}`,
				youthId,
				name: str(c.displayName) ?? str(c.name) ?? `Candidato ${i + 1}`,
				score: num(c.score),
				commuteMin: num(c.commuteMin),
				dailyCost: num(c.dailyCost),
				skillCoverage: num(c.skillCoverage),
				reason: str(c.reason) ?? str(c.explanation),
			},
		];
	});
}

function parsePairs(raw: unknown): BiasPair[] {
	if (!Array.isArray(raw)) return [];
	return raw.flatMap((p): BiasPair[] => {
		if (!isRec(p)) return [];
		const original = str(p.original);
		const variant = str(p.variant);
		if (!original || !variant) return [];
		return [
			{
				original,
				variant,
				scoreOriginal: num(p.scoreOriginal),
				scoreVariant: num(p.scoreVariant),
				changed: typeof p.changed === "boolean" ? p.changed : undefined,
			},
		];
	});
}

function stringify(v: unknown) {
	if (typeof v === "string") return v;
	try {
		return JSON.stringify(v);
	} catch {
		return String(v);
	}
}

export function parseProposal(task: ReviewTask): ParsedProposal {
	const p: Rec = isRec(task.proposal) ? task.proposal : {};
	return {
		subject: str(p.postingTitle) ?? str(p.title),
		company: str(p.company),
		vacancies: num(p.vacancies),
		findings: parseFindings(p.findings),
		originalText: str(p.originalText),
		suggestedText: str(p.suggestedText),
		candidates: parseCandidates(p.candidates),
		variable: str(p.variable),
		parity: num(p.parity),
		threshold: num(p.threshold),
		pairs: parsePairs(p.pairs),
		extra: Object.entries(p)
			.filter(([k]) => !KNOWN.has(k))
			.map(([k, v]) => [k, stringify(v)]),
	};
}

export const kindMeta: Record<ReviewKind, { label: string; short: string }> = {
	bloqueo_oferta: { label: "Bloqueo de oferta", short: "Bloqueo" },
	lista_corta: { label: "Lista corta", short: "Lista corta" },
	alerta_sesgo: { label: "Alerta de sesgo", short: "Sesgo" },
};

/** Qué está en juego, en una línea, para la columna "Impacto". */
export function impactOf(task: ReviewTask, p: ParsedProposal): string {
	switch (task.kind) {
		case "bloqueo_oferta": {
			const v = p.vacancies;
			return v
				? `Oferta sin publicar · ${v} ${v === 1 ? "vacante" : "vacantes"}`
				: "Oferta sin publicar";
		}
		case "lista_corta": {
			const n = p.candidates.length;
			return n
				? `${n} ${n === 1 ? "candidato espera" : "candidatos esperan"} envío`
				: "Lista corta sin enviar";
		}
		case "alerta_sesgo":
			return p.parity != null
				? `Corrida retenida · paridad ${p.parity.toFixed(2)}`
				: "Corrida retenida";
	}
}

const rtf = new Intl.RelativeTimeFormat("es", { numeric: "auto" });

/** "hace 12 min", "hace 3 h", "ayer". */
export function timeAgo(iso: string, now = Date.now()): string {
	const minutes = Math.round((new Date(iso).getTime() - now) / 60_000);
	const abs = Math.abs(minutes);
	if (abs < 1) return "ahora";
	if (abs < 60) return rtf.format(minutes, "minute");
	if (abs < 60 * 24) return rtf.format(Math.round(minutes / 60), "hour");
	return rtf.format(Math.round(minutes / (60 * 24)), "day");
}
