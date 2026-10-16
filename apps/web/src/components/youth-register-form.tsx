"use client";

import { Button } from "@puente/ui/components/button";
import { Input } from "@puente/ui/components/input";
import { Label } from "@puente/ui/components/label";
import { cn } from "@puente/ui/lib/utils";
import { TriangleAlert } from "lucide-react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";

import { createYouth } from "@/lib/api/agents";
import type { Location, TimeSlot, YouthCreate } from "@/lib/api/client";
import { rememberYouth } from "@/lib/youth-session";

const DAYS: { id: TimeSlot["day"]; label: string; short: string }[] = [
	{ id: "lun", label: "Lunes", short: "Lun" },
	{ id: "mar", label: "Martes", short: "Mar" },
	{ id: "mie", label: "Miércoles", short: "Mié" },
	{ id: "jue", label: "Jueves", short: "Jue" },
	{ id: "vie", label: "Viernes", short: "Vie" },
	{ id: "sab", label: "Sábado", short: "Sáb" },
	{ id: "dom", label: "Domingo", short: "Dom" },
];

const COMMUTE = [30, 45, 60, 75, 90, 120];

const GENDERS: { value: NonNullable<YouthCreate["gender"]>; label: string }[] =
	[
		{ value: "femenino", label: "Femenino" },
		{ value: "masculino", label: "Masculino" },
		{ value: "otro", label: "Otro" },
		{ value: "prefiero_no_decir", label: "Prefiero no decir" },
	];

const field =
	"h-11 w-full border border-input bg-transparent px-3 text-base outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50 aria-invalid:border-destructive dark:bg-input/30";

type Field =
	| "displayName"
	| "birthYear"
	| "locationId"
	| "transportBudgetDaily"
	| "minSalary"
	| "availability";

export function YouthRegisterForm({ locations }: { locations: Location[] }) {
	const router = useRouter();
	const base = useId();
	const id = (name: string) => `${base}-${name}`;
	const formRef = useRef<HTMLFormElement>(null);

	const [days, setDays] = useState<Set<TimeSlot["day"]>>(
		new Set(["lun", "mar", "mie", "jue", "vie"]),
	);
	const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
	const [submitError, setSubmitError] = useState<string | null>(null);
	const [pending, setPending] = useState(false);

	const byDistrict = Map.groupBy(
		locations,
		(l) => `${l.distrito}, ${l.provincia}`,
	);

	function validate(fd: FormData) {
		const e: Partial<Record<Field, string>> = {};
		const name = String(fd.get("displayName") ?? "").trim();
		if (!name) e.displayName = "Escribe cómo quieres que te llamemos.";
		const year = Number(fd.get("birthYear"));
		if (!Number.isInteger(year) || year < 1990 || year > 2010)
			e.birthYear = "Usa un año entre 1990 y 2010.";
		if (!fd.get("locationId")) e.locationId = "Elige tu corregimiento.";
		const budget = Number(fd.get("transportBudgetDaily"));
		if (fd.get("transportBudgetDaily") === "" || budget < 0 || budget > 50)
			e.transportBudgetDaily = "Indica un monto entre B/. 0 y B/. 50.";
		const salary = fd.get("minSalary");
		if (salary !== "" && (Number(salary) < 0 || Number(salary) > 5000))
			e.minSalary = "Indica un monto entre B/. 0 y B/. 5000, o déjalo vacío.";
		const start = String(fd.get("start"));
		const end = String(fd.get("end"));
		if (days.size === 0) e.availability = "Marca al menos un día.";
		else if (!start || !end || start >= end)
			e.availability = "La hora de salida debe ser después de la de entrada.";
		return e;
	}

	async function onSubmit(ev: React.FormEvent<HTMLFormElement>) {
		ev.preventDefault();
		setSubmitError(null);
		const fd = new FormData(ev.currentTarget);
		const e = validate(fd);
		setErrors(e);
		const first = Object.keys(e)[0];
		if (first) {
			formRef.current
				?.querySelector<HTMLElement>(`[data-field="${first}"]`)
				?.focus();
			return;
		}

		const start = String(fd.get("start"));
		const end = String(fd.get("end"));
		const gender = fd.get("gender");
		const body: YouthCreate = {
			displayName: String(fd.get("displayName")).trim(),
			birthYear: Number(fd.get("birthYear")),
			gender: GENDERS.find((g) => g.value === gender)?.value,
			locationId: String(fd.get("locationId")),
			maxCommuteMin: Number(fd.get("maxCommuteMin")),
			transportBudgetDaily: Number(fd.get("transportBudgetDaily")),
			minSalary:
				fd.get("minSalary") === "" ? undefined : Number(fd.get("minSalary")),
			studying: fd.get("studying") === "on",
			availability: DAYS.filter((d) => days.has(d.id)).map((d) => ({
				day: d.id,
				start,
				end,
			})),
		};

		setPending(true);
		const result = await createYouth(body);
		if (!result.ok) {
			setPending(false);
			setSubmitError(result.message);
			return;
		}
		rememberYouth(result.data.id);
		router.push(`/joven/perfil?id=${result.data.id}` as Route);
	}

	const describe = (name: Field, hint?: string) => ({
		"aria-invalid": errors[name] ? true : undefined,
		"aria-describedby":
			[hint, errors[name] ? id(`${name}-error`) : null]
				.filter(Boolean)
				.join(" ") || undefined,
		"data-field": name,
	});

	const errorText = (name: Field) =>
		errors[name] ? (
			<p
				id={id(`${name}-error`)}
				className="flex items-start gap-1.5 text-danger-fg text-sm"
			>
				<TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
				{errors[name]}
			</p>
		) : null;

	const labelCls = "font-medium text-sm";

	return (
		<form
			ref={formRef}
			onSubmit={onSubmit}
			noValidate
			className="flex flex-col gap-8"
		>
			<fieldset className="flex flex-col gap-4">
				<legend className="mb-4 font-semibold text-lg">Sobre ti</legend>
				<div className="flex flex-col gap-2">
					<Label htmlFor={id("displayName")} className={labelCls}>
						¿Cómo te llamamos?
					</Label>
					<Input
						id={id("displayName")}
						name="displayName"
						autoComplete="given-name"
						maxLength={120}
						className="h-11 text-base md:text-base"
						{...describe("displayName")}
					/>
					{errorText("displayName")}
				</div>
				<div className="grid gap-4 sm:grid-cols-2">
					<div className="flex flex-col gap-2">
						<Label htmlFor={id("birthYear")} className={labelCls}>
							Año de nacimiento
						</Label>
						<Input
							id={id("birthYear")}
							name="birthYear"
							type="number"
							inputMode="numeric"
							min={1990}
							max={2010}
							placeholder="2004"
							className="h-11 text-base md:text-base"
							{...describe("birthYear")}
						/>
						{errorText("birthYear")}
					</div>
					<div className="flex flex-col gap-2">
						<Label htmlFor={id("gender")} className={labelCls}>
							Género{" "}
							<span className="font-normal text-muted-foreground">
								(opcional)
							</span>
						</Label>
						<select
							id={id("gender")}
							name="gender"
							defaultValue=""
							className={field}
						>
							<option value="">Sin indicar</option>
							{GENDERS.map((g) => (
								<option key={g.value} value={g.value}>
									{g.label}
								</option>
							))}
						</select>
					</div>
				</div>
				<p className="text-muted-foreground text-sm">
					El género no se usa para emparejarte: el Auditor comprueba que
					cambiarlo no cambie tus resultados.
				</p>
				<label className="flex min-h-11 items-center gap-3 text-sm">
					<input
						type="checkbox"
						name="studying"
						className="size-5 accent-primary"
					/>
					Estoy estudiando
				</label>
			</fieldset>

			<fieldset className="flex flex-col gap-4">
				<legend className="mb-4 font-semibold text-lg">Cómo te mueves</legend>
				<div className="flex flex-col gap-2">
					<Label htmlFor={id("locationId")} className={labelCls}>
						¿En qué corregimiento vives?
					</Label>
					<select
						id={id("locationId")}
						name="locationId"
						defaultValue=""
						className={field}
						{...describe("locationId")}
					>
						<option value="" disabled>
							Elige uno
						</option>
						{[...byDistrict].map(([district, items]) => (
							<optgroup key={district} label={district}>
								{items.map((l) => (
									<option key={l.id} value={l.id}>
										{l.corregimiento}
									</option>
								))}
							</optgroup>
						))}
					</select>
					{errorText("locationId")}
				</div>
				<div className="grid gap-4 sm:grid-cols-2">
					<div className="flex flex-col gap-2">
						<Label htmlFor={id("maxCommuteMin")} className={labelCls}>
							Tiempo máximo de viaje
						</Label>
						<select
							id={id("maxCommuteMin")}
							name="maxCommuteMin"
							defaultValue="60"
							className={field}
						>
							{COMMUTE.map((m) => (
								<option key={m} value={m}>
									{m} min por trayecto
								</option>
							))}
						</select>
					</div>
					<div className="flex flex-col gap-2">
						<Label htmlFor={id("transportBudgetDaily")} className={labelCls}>
							Pasaje al día (B/.)
						</Label>
						<Input
							id={id("transportBudgetDaily")}
							name="transportBudgetDaily"
							type="number"
							inputMode="decimal"
							min={0}
							max={50}
							step={0.25}
							defaultValue="2.50"
							className="tabular h-11 font-mono text-base md:text-base"
							{...describe("transportBudgetDaily", id("budget-hint"))}
						/>
						<p id={id("budget-hint")} className="text-muted-foreground text-xs">
							Ida y vuelta, lo que puedes gastar sin problema.
						</p>
						{errorText("transportBudgetDaily")}
					</div>
				</div>
				<div className="flex flex-col gap-2">
					<Label htmlFor={id("minSalary")} className={labelCls}>
						Salario mínimo que aceptarías (B/. al mes){" "}
						<span className="font-normal text-muted-foreground">
							(opcional)
						</span>
					</Label>
					<Input
						id={id("minSalary")}
						name="minSalary"
						type="number"
						inputMode="numeric"
						min={0}
						max={5000}
						step={10}
						placeholder="600"
						className="tabular h-11 font-mono text-base md:text-base"
						{...describe("minSalary")}
					/>
					{errorText("minSalary")}
				</div>
			</fieldset>

			<fieldset
				className="flex flex-col gap-4"
				aria-describedby={
					errors.availability ? id("availability-error") : undefined
				}
			>
				<legend className="mb-4 font-semibold text-lg">
					¿Cuándo puedes trabajar?
				</legend>
				<div className="grid grid-cols-4 gap-2 sm:grid-cols-7">
					{DAYS.map((d, i) => {
						const checked = days.has(d.id);
						return (
							<label
								key={d.id}
								className={cn(
									"flex min-h-11 cursor-pointer items-center justify-center border text-sm transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring/50",
									checked
										? "border-primary bg-primary text-primary-foreground"
										: "hover:bg-muted",
								)}
							>
								<input
									type="checkbox"
									className="sr-only"
									checked={checked}
									data-field={i === 0 ? "availability" : undefined}
									onChange={() =>
										setDays((prev) => {
											const next = new Set(prev);
											if (next.has(d.id)) next.delete(d.id);
											else next.add(d.id);
											return next;
										})
									}
								/>
								<span aria-hidden="true">{d.short}</span>
								<span className="sr-only">{d.label}</span>
							</label>
						);
					})}
				</div>
				<div className="grid grid-cols-2 gap-4">
					<div className="flex flex-col gap-2">
						<Label htmlFor={id("start")} className={labelCls}>
							Desde
						</Label>
						<input
							id={id("start")}
							name="start"
							type="time"
							defaultValue="08:00"
							className={cn(field, "tabular font-mono")}
						/>
					</div>
					<div className="flex flex-col gap-2">
						<Label htmlFor={id("end")} className={labelCls}>
							Hasta
						</Label>
						<input
							id={id("end")}
							name="end"
							type="time"
							defaultValue="17:00"
							className={cn(field, "tabular font-mono")}
						/>
					</div>
				</div>
				{errorText("availability")}
			</fieldset>

			{submitError ? (
				<p
					role="alert"
					className="flex items-start gap-2 border border-danger/40 bg-danger/5 p-4 text-sm"
				>
					<TriangleAlert
						className="mt-0.5 size-4 shrink-0 text-danger-fg"
						aria-hidden="true"
					/>
					<span>
						<span className="font-medium text-danger-fg">
							No pudimos crear tu perfil.
						</span>{" "}
						{submitError}
					</span>
				</p>
			) : null}

			<Button
				type="submit"
				size="lg"
				className="h-12 w-full text-base"
				disabled={pending}
			>
				{pending ? "Creando tu perfil…" : "Continuar"}
			</Button>
		</form>
	);
}
