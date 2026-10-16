import type { TimeSlot } from "@/lib/api/client";

const DAY_ORDER = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"] as const;
const DAY_LABEL: Record<TimeSlot["day"], string> = {
	lun: "lun",
	mar: "mar",
	mie: "mié",
	jue: "jue",
	vie: "vie",
	sab: "sáb",
	dom: "dom",
};

const balboas = new Intl.NumberFormat("es-PA", { maximumFractionDigits: 0 });

/** "B/. 650–700" o "desde B/. 640". */
export function formatSalary(min?: number, max?: number): string | null {
	if (min == null && max == null) return null;
	if (min != null && max != null && max !== min) {
		return `B/. ${balboas.format(min)}–${balboas.format(max)}`;
	}
	if (min != null)
		return max == null
			? `desde B/. ${balboas.format(min)}`
			: `B/. ${balboas.format(min)}`;
	return `hasta B/. ${balboas.format(max as number)}`;
}

/** Agrupa días consecutivos con el mismo horario: "lun–vie 08:00–16:00 · sáb 07:00–12:00". */
export function formatSchedule(slots: TimeSlot[] = []): string | null {
	if (slots.length === 0) return null;
	const sorted = [...slots].sort(
		(a, b) => DAY_ORDER.indexOf(a.day) - DAY_ORDER.indexOf(b.day),
	);
	const groups: {
		from: TimeSlot["day"];
		to: TimeSlot["day"];
		start: string;
		end: string;
	}[] = [];
	for (const slot of sorted) {
		const last = groups.at(-1);
		const contiguous =
			last &&
			last.start === slot.start &&
			last.end === slot.end &&
			DAY_ORDER.indexOf(slot.day) === DAY_ORDER.indexOf(last.to) + 1;
		if (contiguous) last.to = slot.day;
		else
			groups.push({
				from: slot.day,
				to: slot.day,
				start: slot.start,
				end: slot.end,
			});
	}
	return groups
		.map((g) => {
			const days =
				g.from === g.to
					? DAY_LABEL[g.from]
					: `${DAY_LABEL[g.from]}–${DAY_LABEL[g.to]}`;
			return `${days} ${g.start}–${g.end}`;
		})
		.join(" · ");
}

export function plural(n: number, one: string, many: string) {
	return `${n} ${n === 1 ? one : many}`;
}
