// Построение диаграмм классов проекта по JSON, извлечённому из исходного кода.
const fs = require("fs"), sharp = require("sharp");
const КЛ = JSON.parse(fs.readFileSync("diagrams/classes.json", "utf8"));
const FONT = "Arial", LH = 16, FZ = 12;
const width = t => t.length * 6.5 + 24;

const ASSOC = [
  ["Пилот", "СессияТестирования", "проходит", "1", "N"], ["СессияТестирования", "ТаблицаШульте", "включает", "1", "N"],
  ["СессияТестирования", "РезультатТестирования", "формирует", "1", "1"],
  ["РезультатТестирования", "ЗаключениеОДопуске", "служит основанием", "1", "N"],
  ["НормаДопуска", "ЗаключениеОДопуске", "применяется в", "1", "N"], ["СводныйОтчёт", "Пилот", "включает", "M", "N"]];
const GEN = [["Пилот", "Пользователь"]];
const COMP = [["СводныйОтчёт", "СтрокаОтчёта", "содержит", "1", "N"]];
const T = (t, x, y, o = {}) => `<text x="${x}" y="${y}" font-size="${o.fs || 12.5}" font-family="${FONT}" ${o.it ? 'font-style="italic"' : ""} ${o.b ? 'font-weight="bold"' : ""} text-anchor="${o.a || "middle"}">${t}</text>`;
const LINE = (x1, y1, x2, y2, dash) => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="black" stroke-width="1.6" ${dash ? 'stroke-dasharray="7,5"' : ""}/>`;

function строкиКласса(имя, фильтр, скрыть) {
  const к = КЛ[имя];
  const атр = к.атрибуты.map(а => `${а.вид}${а.имя.replace(/^_+/, "")}${а.тип ? ": " + а.тип : ""}${а.знач ? " = " + а.знач : ""}`);
  let оп = к.операции.filter(о => !(фильтр && !фильтр.includes(о.имя)) && !(скрыть && скрыть.includes(о.имя)));
  const опТекст = оп.map(о => `${о.вид}${о.имя.replace(/^_+/, "")}(${о.парам.map(п => п[0] + (п[1] ? ": " + п[1] : "")).join(", ")})${о.возвр ? ": " + о.возвр : ""}`);
  const обернуть = (т, макс = 50) => {
    if (т.length <= макс) return [т];
    const части = т.split(", "), строки = []; let тек = "";
    for (const ч of части) {
      const кандидат = тек ? тек + ", " + ч : ч;
      if (кандидат.length > макс && тек) { строки.push(тек + ","); тек = "    " + ч; } else тек = кандидат;
    }
    if (тек) строки.push(тек);
    // слишком длинное значение возврата: переносим по двоеточию
    return строки.flatMap(л => л.length > макс + 12 && л.includes("): ") ? [л.slice(0, л.indexOf("): ") + 2).trimEnd(), "    " + л.slice(л.indexOf("): ") + 3)] : [л]);
  };
  return { атр: атр.flatMap(a => обернуть(a)), оп: опТекст.flatMap(o => обернуть(o)), стерео: к.стереотип };
}
function бокс(имя, x, y, опц = {}) {
  const { атр, оп, стерео } = строкиКласса(имя, опц.фильтр, опц.скрыть);
  const w = Math.max(250, width(имя) + 20, ...атр.map(width), ...оп.map(width));
  const hH = стерео ? 46 : 30, hA = Math.max(1, атр.length) * LH + 10, hO = Math.max(1, оп.length) * LH + 10, h = hH + hA + hO;
  let s = `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="white" stroke="black" stroke-width="1.8"/>`;
  if (стерео) s += T("«" + стерео + "»", x + w / 2, y + 17, { it: true, fs: 11.5 });
  s += T(имя, x + w / 2, y + (стерео ? 37 : 20), { b: true, fs: 14 });
  s += `<line x1="${x}" y1="${y + hH}" x2="${x + w}" y2="${y + hH}" stroke="black" stroke-width="1.4"/><line x1="${x}" y1="${y + hH + hA}" x2="${x + w}" y2="${y + hH + hA}" stroke="black" stroke-width="1.4"/>`;
  атр.forEach((a, i) => s += T(a, x + 10, y + hH + 16 + i * LH, { a: "start", fs: FZ }));
  оп.forEach((o, i) => s += T(o, x + 10, y + hH + hA + 16 + i * LH, { a: "start", fs: FZ }));
  return { svg: s, x, y, w, h, right: x + w, bottom: y + h, cx: x + w / 2, cy: y + h / 2 };
}
async function сохранить(файл, тело, mx, my) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${mx} ${my}" width="${mx}" height="${my}"><rect width="${mx}" height="${my}" fill="white"/>${тело}</svg>`;
  fs.writeFileSync(`diagrams/${файл}.svg`, svg);
  await sharp(Buffer.from(svg), { density: 200 }).png().toFile(`diagrams/${файл}.png`);
}

// ---------- диаграммы по прецедентам ----------
const UC = [
  { f: "d1", F: "ФормаВхода", C: "КонтроллерАутентификации", ent: ["Пользователь"], oth: [["Сеанс", "C"]] },
  { f: "d2", F: "ФормаТестирования", C: "КонтроллерТестирования", ent: ["ТаблицаШульте", "СессияТестирования", "РезультатТестирования"], oth: [["Секундомер", "F"]] },
  { f: "d3", F: "ФормаМоихРезультатов", C: "КонтроллерРезультатовПилота", ent: ["СессияТестирования", "РезультатТестирования"], oth: [] },
  { f: "d4", F: "ФормаНазначенияТестирования", C: "КонтроллерНазначения", ent: ["Пилот", "СессияТестирования"], oth: [["IИнтерфейсУведомлений", "C"]] },
  { f: "d5", F: "ФормаРезультатовПилота", C: "КонтроллерРезультатов", ent: ["ТаблицаШульте", "СессияТестирования", "РезультатТестирования"], oth: [["ДеталиСессии", "C"]] },
  { f: "d6", F: "ФормаЗаключения", C: "КонтроллерЗаключения", ent: ["РезультатТестирования", "ЗаключениеОДопуске", "НормаДопуска"],
    oth: [["ПредварительноеЗаключение", "C"], ["ОценкаДопуска", "C"], ["IИнтерфейсСлужбыБезопасности", "C"]] },
  { f: "d7", F: "ФормаДинамики", C: "КонтроллерДинамики", ent: ["Пилот", "СессияТестирования", "РезультатТестирования"], oth: [["ГрафикДинамики", "F"], ["АнализДинамики", "C"]] },
  { f: "d8", F: "ФормаДанныхПилотов", C: "КонтроллерДанныхПилотов", ent: ["Пользователь", "Пилот", "СессияТестирования"], oth: [["ДанныеПилота", "C"]] },
  { f: "d9", F: "ФормаНормДопуска", C: "КонтроллерНорм", ent: ["НормаДопуска"], oth: [] },
  { f: "d10", F: "ФормаСводногоОтчёта", C: "КонтроллерОтчётов", ent: ["СтрокаОтчёта", "СводныйОтчёт", "Пилот", "РезультатТестирования"],
    oth: [["IИнтерфейсСлужбыБезопасности", "C"], ["СервисОтчётов", "C"]] }
];
function фильтрИнтерфейса(имя, кк) {
  const в = КЛ[кк].вызовы;
  if (имя === "IХранилище") return в["_хранилище"] || [];
  if (имя === "IИнтерфейсУведомлений") return в["_уведомления"] || [];
  if (имя === "IИнтерфейсСлужбыБезопасности") return в["_служба"] || [];
  return null;
}
async function диаграммаПрецедента(u) {
  const мк = { фильтр: null };
  const bF = бокс(u.F, 0, 0), bC = бокс(u.C, 0, 0);
  const стек = [...u.ent.map(n => ({ n, ...{ b: бокс(n, 0, 0) } })), { n: "IХранилище", b: бокс("IХранилище", 0, 0, { фильтр: фильтрИнтерфейса("IХранилище", u.C) }) }];
  const др = u.oth.map(([n, ссылка]) => ({ n, ссылка, b: бокс(n, 0, 0, { фильтр: фильтрИнтерфейса(n, u.C) }) }));
  const w0 = Math.max(bF.w, ...др.map(д => д.b.w)), w1 = bC.w, w2 = Math.max(...стек.map(с => с.b.w));
  const x0 = 40, x1 = x0 + w0 + 100, x2 = x1 + w1 + 120;
  // столбец 3
  let y = 40; const поз = [];
  стек.forEach((с, i) => { const b = бокс(с.n, x2, y, { фильтр: i === стек.length - 1 ? фильтрИнтерфейса("IХранилище", u.C) : null }); поз.push(b); y = b.bottom + (i < стек.length - 2 ? 72 : 45); });
  const верх = 40, низ = поз[поз.length - 1].bottom, центр = (верх + низ) / 2;
  const C = бокс(u.C, x1, Math.max(40, центр - bC.h / 2));
  const F = бокс(u.F, x0, C.cy - bF.h / 2);
  let yy = F.bottom + 45; const бдр = [];
  др.forEach(д => { const b = бокс(д.n, x0, yy, { фильтр: фильтрИнтерфейса(д.n, u.C) }); бдр.push(b); yy = b.bottom + 45; });
  let линии = "", подписи = "";
  // форма — контроллер
  линии += LINE(F.right, C.cy, C.x, C.cy, true);
  // контроллер — сущности и хранилище
  const m = поз.length;
  поз.forEach((b, j) => { const off = (j - (m - 1) / 2) * 16; линии += LINE(C.right, Math.max(C.y + 14, Math.min(C.bottom - 14, C.cy + off)), b.x, b.cy, true); });
  // прочие классы слева
  let k = 0;
  др.forEach((д, i) => {
    const b = бдр[i];
    if (д.ссылка === "F" && i === 0) линии += LINE(F.x + 50, F.bottom, F.x + 50, b.y, true);
    else { k++; линии += LINE(b.right, b.cy, C.x, Math.min(C.bottom - 12, C.cy + k * 18), true); }
  });
  // связи между сущностями (соседние в стеке)
  const имена = стек.map(с => с.n);
  const вертикаль = (a, b, название, ma, mb, тип) => {
    const ia = имена.indexOf(a), ib = имена.indexOf(b);
    if (ia < 0 || ib < 0) return;
    if (Math.abs(ia - ib) !== 1) { console.log("  предупреждение: несоседние", a, b); return; }
    const вв = ia < ib ? поз[ia] : поз[ib], нн = ia < ib ? поз[ib] : поз[ia], x = вв.x + Math.min(вв.w, нн.w) / 2;
    const верхнее = ia < ib ? a : b;
    линии += LINE(x, вв.bottom, x, нн.y);
    if (тип === "gen") {
      if (верхнее === b) линии += `<polygon points="${x},${вв.bottom} ${x - 9},${вв.bottom + 16} ${x + 9},${вв.bottom + 16}" fill="white" stroke="black" stroke-width="1.6"/>`;
      return;
    }
    const my = (вв.bottom + нн.y) / 2, mВ = ia < ib ? ma : mb, mН = ia < ib ? mb : ma;
    подписи += T(название, x + 14, my + 4, { it: true, a: "start" }) + T(mВ, x + 12, вв.bottom + 17, { b: true, a: "start", fs: 13 }) + T(mН, x + 12, нн.y - 8, { b: true, a: "start", fs: 13 });
    if (тип === "comp") { const wh = верхнее === a ? вв : нн; const yb = верхнее === a ? вв.bottom : нн.y; const d = верхнее === a ? 1 : -1; линии += `<polygon points="${x},${yb} ${x - 8},${yb + 11 * d} ${x},${yb + 22 * d} ${x + 8},${yb + 11 * d}" fill="black"/>`; }
  };
  GEN.forEach(([sub, sup]) => вертикаль(sub, sup, "", "", "", "gen"));
  ASSOC.forEach(([a, b, н, ma, mb]) => вертикаль(a, b, н, ma, mb, "assoc"));
  COMP.forEach(([a, b, н, ma, mb]) => вертикаль(a, b, н, ma, mb, "comp"));
  const все = [F, C, ...бдр, ...поз];
  const mx = Math.max(...все.map(b => b.right)) + 40, my = Math.max(...все.map(b => b.bottom)) + 30;
  await сохранить(u.f, линии + подписи + все.map(b => b.svg).join(""), mx, my);
  console.log(u.f, Math.round(mx), Math.round(my));
}

(async () => { for (const u of UC) await диаграммаПрецедента(u); await require("./arch_gen.js")(КЛ, бокс, сохранить, T, LINE, строкиКласса); })();
