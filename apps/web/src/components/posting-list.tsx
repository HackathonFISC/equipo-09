import { cn } from "@puente/ui/lib/utils";
import {
	Ban,
	CalendarClock,
	CircleCheck,
	CircleDashed,
	FileText,
	type LucideIcon,
	MapPin,
	Users,
	Wallet,
} from "lucide-react";

import type { JobPosting, PostingStatus } from "@/lib/api/client";
import { formatSalary, formatSchedule, plural } from "@/lib/format";

export const postingStatusMeta: Record<
	PostingStatus,
	{ label: string; icon: LucideIcon; className: string }
> = {
	publicada: {
		label: "Publicada",
		icon: CircleCheck,
		className: "text-success-fg",
	},
	bloqueada: { label: "Bloqueada", icon: Ban, className: "text-danger-fg" },
	borrador: {
		label: "Borrador",
		icon: CircleDashed,
		className: "text-muted-foreground",
	},
	cerrada: {
		label: "Cerrada",
		icon: FileText,
		className: "text-muted-foreground",
	},
};

export function PostingStatusBadge({ status }: { status: PostingStatus }) {
	const { label, icon: Icon, className } = postingStatusMeta[status];
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

function Fact({
	icon: Icon,
	children,
}: {
	icon: LucideIcon;
	children: React.ReactNode;
}) {
	return (
		<span className="inline-flex items-center gap-1.5">
			<Icon
				className="size-4 shrink-0 text-muted-foreground"
				aria-hidden="true"
			/>
			{children}
		</span>
	);
}

function PostingRow({ posting }: { posting: JobPosting }) {
	const salary = formatSalary(posting.salaryMin, posting.salaryMax);
	const schedule = formatSchedule(posting.schedule);
	const failedAudits = (posting.auditFindings ?? []).filter((a) => !a.passed);

	return (
		<li className="flex flex-col gap-3 border-b py-5 last:border-b-0">
			<div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
				<h3 className="font-semibold text-base">{posting.title}</h3>
				<PostingStatusBadge status={posting.status} />
			</div>

			<p className="flex flex-wrap gap-x-5 gap-y-1.5 text-sm">
				{posting.location ? (
					<Fact icon={MapPin}>
						{posting.location.corregimiento}, {posting.location.distrito}
					</Fact>
				) : null}
				{salary ? (
					<Fact icon={Wallet}>
						<span className="tabular font-mono">{salary}</span>
					</Fact>
				) : null}
				{schedule ? (
					<Fact icon={CalendarClock}>
						<span className="tabular font-mono">{schedule}</span>
					</Fact>
				) : null}
				{posting.vacancies ? (
					<Fact icon={Users}>
						{plural(posting.vacancies, "vacante", "vacantes")}
					</Fact>
				) : null}
			</p>

			{posting.requirements.length > 0 ? (
				<ul
					aria-label="Habilidades requeridas"
					className="flex flex-wrap gap-1.5"
				>
					{posting.requirements.map((req) => (
						<li
							key={req.skill.id}
							className={cn(
								"border px-2 py-0.5 text-xs",
								req.required
									? "border-primary/30 bg-secondary text-secondary-foreground"
									: "text-muted-foreground",
							)}
						>
							{req.skill.labelEs}
							<span className="sr-only">
								{req.required ? " (obligatoria)" : " (deseable)"}
							</span>
							{req.required ? null : (
								<span aria-hidden="true"> · deseable</span>
							)}
						</li>
					))}
				</ul>
			) : null}

			{failedAudits.length > 0 ? (
				<div className="flex flex-col gap-1.5 border border-danger/30 bg-danger/5 px-3 py-2.5 text-sm">
					<p className="font-medium text-danger-fg">
						El Auditor detuvo esta oferta. Un orientador decide si se publica.
					</p>
					<ul className="flex list-disc flex-col gap-1 pl-5 text-foreground/90">
						{failedAudits.flatMap((audit) =>
							(audit.findings ?? []).map((finding) => (
								<li key={`${audit.id}-${finding}`}>{finding}</li>
							)),
						)}
					</ul>
				</div>
			) : null}
		</li>
	);
}

export function PostingList({ postings }: { postings: JobPosting[] }) {
	return (
		<ul className="flex flex-col border-y">
			{postings.map((posting) => (
				<PostingRow key={posting.id} posting={posting} />
			))}
		</ul>
	);
}
