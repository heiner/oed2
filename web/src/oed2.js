const SECTION_D_START = 0x0b01ce00;
const BODY_BLOCK_STRIDE = 0x8000;
const BODY_BLOCK_RESIDUE = 0x1000;
const BODY_HEADER_BYTES = 16;
const BODY_CONTROL_OFFSET = 0x16701000;
const BODY_CONTROL_WORDS = 9;
const BODY_AUX_PREFIX_WORDS = 64;

const OED_LISTS = {
  word: { control: 0x143f3000, tableA: 0x145fe800, tableB: 0x14602800 },
  phrase: { control: 0x1499f000, tableA: 0x14ac9800, tableB: 0x14acd800 },
};

const ENTITY_SUFFIX_MARKS = {
  acu: "\u0301",
  grave: "\u0300",
  circ: "\u0302",
  tilde: "\u0303",
  uml: "\u0308",
  mac: "\u0304",
  breve: "\u0306",
  hacek: "\u030c",
  dot: "\u0307",
  dotab: "\u0307",
  ced: "\u0327",
  hook: "\u0309",
  ang: "\u030a",
};

const ENTITY_NAME_UNICODE = {
  Alpha: "\u0391",
  Beta: "\u0392",
  Gamma: "\u0393",
  Delta: "\u0394",
  Epsilon: "\u0395",
  Zeta: "\u0396",
  Eta: "\u0397",
  Theta: "\u0398",
  Iota: "\u0399",
  Kappa: "\u039a",
  Lambda: "\u039b",
  Mu: "\u039c",
  Nu: "\u039d",
  Xi: "\u039e",
  Omicron: "\u039f",
  Pi: "\u03a0",
  Rho: "\u03a1",
  Sigma: "\u03a3",
  Tau: "\u03a4",
  Upsilon: "\u03a5",
  Phi: "\u03a6",
  Chi: "\u03a7",
  Psi: "\u03a8",
  Omega: "\u03a9",
  alpha: "\u03b1",
  beta: "\u03b2",
  gamma: "\u03b3",
  delta: "\u03b4",
  epsilon: "\u03b5",
  zeta: "\u03b6",
  eta: "\u03b7",
  theta: "\u03b8",
  iota: "\u03b9",
  kappa: "\u03ba",
  lambda: "\u03bb",
  mu: "\u03bc",
  nu: "\u03bd",
  xi: "\u03be",
  omicron: "\u03bf",
  pi: "\u03c0",
  rho: "\u03c1",
  sigma: "\u03c3",
  Csigma: "\u03c2",
  tau: "\u03c4",
  upsilon: "\u03c5",
  phi: "\u03c6",
  chi: "\u03c7",
  psi: "\u03c8",
  omega: "\u03c9",
  th: "\u00fe",
  Th: "\u00de",
  edh: "\u00f0",
  Edh: "\u00d0",
  ae: "\u00e6",
  Ae: "\u00c6",
  oe: "\u0153",
  Oe: "\u0152",
  ygh: "\u021d",
  Ygh: "\u021c",
  schwa: "\u0259",
  longs: "\u017f",
  eszett: "\u00df",
  wyn: "\u01bf",
  oq: "\u2018",
  cq: "\u2019",
  oqq: "\u201c",
  cqq: "\u201d",
  osb: "[",
  csb: "]",
  en: "\u2013",
  em: "\u2014",
  emem: "\u2e3a",
  dd: "..",
  ddd: "...",
  es: " ",
  ts: " ",
  fs: "",
  par: "",
  or: "or",
  q: "?",
  mc: "c",
  asg: "ᵹ",
  pp: "″",
  // Greek letters via &i*. (italic / Greek-font slot in OED.EXE)
  ia: "α",
  ib: "β",
  ig: "γ",
  id: "δ",
  ie: "ε",
  iz: "ζ",
  ih: "η",
  iq: "θ",
  // Standalone diacritics (combining marks; the browser composes them onto the preceding character)
  acu: "́",
  grave: "̀",
  circ: "̂",
  tilde: "̃",
  uml: "̈",
  mac: "̄",
  breve: "̆",
  hacek: "̌",
  hook: "̉",
  dotab: "̇",
  dotbl: "̣",
  cdil: "̧",
  ced: "̧",
  undl: "̲",
  circbl: "̥",
  // Classical / paleographic letters
  digamma: "ϝ",
  Digamma: "Ϝ",
  koppa: "ϟ",
  Koppa: "Ϟ",
  sampi: "ϡ",
  Sampi: "Ϡ",
  fsigma: "ς",
  hbar: "ℏ",
  eth: "ð",
  Eth: "Ð",
  Wyn: "Ƿ",
  Tse: "Ц",
  // Apothecary measures
  recipe: "℞",
  ounce: "℥",
  drachm: "ʒ",
  scruple: "℈",
  // Astronomical / zodiac
  aries: "♈",
  taur: "♉",
  canc: "♋",
  leo: "♌",
  virgo: "♍",
  libra: "♎",
  scorpio: "♏",
  sagit: "♐",
  capr: "♑",
  aquar: "♒",
  pisces: "♓",
  earth: "♁",
  jup: "♃",
  saturn: "♄",
  merc: "☿",
  moonfq: "☽",
  moonlq: "☾",
  // Card suits, cross, ankh
  heart: "♥",
  spade: "♠",
  cross: "✝",
  ankh: "☥",
  circle: "○",
  circledot: "⊙",
  // Math / logic
  ergo: "∴",
  since: "∵",
  congr: "≅",
  implies: "⇒",
  notelem: "∉",
  not: "¬",
  expon: "↑",
  equil: "⇌",
  assert: "⊢",
  // Arrows / brackets
  lar: "←",
  lrar: "↔",
  dblar: "⇔",
  dblgt: "»",
  dbllt: "«",
  decr: "↓",
  // Index hand
  index: "☞",
  // Paragraph variants — best-guess Unicode equivalents for OED's medieval paragraph
  // marks; OED.EXE doesn't bind them to specific glyphs we can verify.
  fatpara: "⁋",
  para2: "⸿",
  para3: "❡",
  para4: "⁋",
  para5: "¶",
  // Latin letters with stroke / paleographic shapes
  Lbar: "Ł",
  lbar: "ł",
  Obar: "Ø",
  obar: "ø",
  Abarab: "Ā",
  Tbarab: "T̄",
  tbarab: "t̄",
  hbar2: "ℏ",
  // Punctuation / symbols
  hash: "#",
  caret: "^",
  bslash: "\\",
  amp: "&",
  and: "and",
  sm: "'",
  smm: "\"",
  lt: "<",
  gt: ">",
  times: "\u00d7",
  sect: "\u00a7",
  page: "\u204b",
  para: "\u00b6",
  dag: "\u2020",
  ddag: "\u2021",
  deg: "\u00b0",
  min: "\u2212",
  pm: "\u00b1",
  cent: "\u00a2",
  dollar: "$",
  pstlg: "\u00a3",
  dubh: "~",
  swing: "~",
  vb: "|",
  at: "@",
  sqrt: "\u221a",
  infin: "\u221e",
  ident: "\u2261",
  prop: "\u221d",
  elem: "\u2208",
  union: "\u222a",
  integ: "\u222b",
  le: "\u2264",
  ge: "\u2265",
  slle: "\u2264",
  slge: "\u2265",
  neq: "\u2260",
  div: "\u00f7",
  logicor: "\u2228",
  logicand: "\u2227",
  rar: "\u2192",
  ang: "\u2220",
  flat: "\u266d",
  natural: "\u266e",
  sharp: "\u266f",
  male: "\u2642",
  female: "\u2640",
  tri: "\u25b3",
  square: "\u25a1",
  star: "\u2606",
  a: "a",
  c: "c",
  // Phonetic / consonant marks
  glots: "\u0294",
  click: "\u01c3",
  pharyng: "\u0295",
  // Hebrew letters
  hebaleph: "\u05d0",
  hebbeth: "\u05d1",
  hebgimel: "\u05d2",
  hebdaleth: "\u05d3",
  hebhe: "\u05d4",
  hebwaw: "\u05d5",
  hebzayin: "\u05d6",
  hebcheth: "\u05d7",
  hebteth: "\u05d8",
  hebyod: "\u05d9",
  hebkaph: "\u05db",
  heblamed: "\u05dc",
  hebmem: "\u05de",
  hebnun: "\u05e0",
  hebnunfin: "\u05df",
  hebpe: "\u05e4",
  hebpedag: "\u05e4\u05bc",
  hebqoph: "\u05e7",
  hebresh: "\u05e8",
  hebshin: "\u05e9",
  hebtav: "\u05ea",
  hebtsade: "\u05e6",
  hebayin: "\u05e2",
  ayin: "\u05e2",
  // Hebrew vowel points (niqqud)
  qamets: "\u05b8",
  hireq: "\u05b4",
  segol: "\u05b6",
  sheva: "\u05b0",
  hatpath: "\u05b2",
  hatqam: "\u05b3",
  hatseg: "\u05b1",
  shadda: "\u0651",
  // Cyrillic letters
  cyrO: "\u041e",
  cyrP: "\u0420",
  cyra: "\u0430",
  cyrd: "\u0434",
  cyre: "\u0435",
  cyrm: "\u043c",
  cyrn: "\u043d",
  cyrr: "\u0440",
  cyrt: "\u0442",
  cyry: "\u0443",
  cyrhard: "\u044a",
  cyrsoft: "\u044c",
  cyrjat: "\u0463",
  // Arabic letters (most common; "*full" variants left for now)
  aralif: "\u0627",
  arba: "\u0628",
  arta: "\u062a",
  artha: "\u062b",
  arha: "\u062d",
  ardal: "\u062f",
  arnun: "\u0646",
  arpa: "\u067e",
  arqoph: "\u0642",
  arwaw: "\u0648",
  arya: "\u064a",
  arain: "\u0639",
  arTa: "\u0637",
  arHa: "\u0647",
  arzero: "\u0660",
  // Greek paleographic / archaic letterforms \u2014 render as the modern Greek letter
  egchi: "\u03c7",
  eggamma1: "\u03b3",
  eggamma2: "\u03b3",
  egiota: "\u03b9",
  egkappa: "\u03ba",
  eglambda: "\u03bb",
  egmu1: "\u03bc",
  egmu2: "\u03bc",
  egnu1: "\u03bd",
  egnu2: "\u03bd",
  egpi1: "\u03c0",
  egpi2: "\u03c0",
  egpi3: "\u03c0",
  egrho1: "\u03c1",
  egrho2: "\u03c1",
  egsampi: "\u03e1",
  egsan: "\u03fb",
  egsigma1: "\u03c3",
  egsigma2: "\u03c3",
  egxi1: "\u03be",
  egxi2: "\u03be",
  egxi3: "\u03be",
  // Mathematical alphanumeric \u2014 Fraktur capitals
  frakB: "\ud835\udd05",
  frakG: "\ud835\udd0a",
  frakH: "\u210c",
  frakI: "\u2111",
  frakM: "\ud835\udd10",
  frakU: "\ud835\udd18",
  frakX: "\ud835\udd1b",
  frakY: "\ud835\udd1c",
  frakh: "\ud835\udd25",
  // Mathematical alphanumeric \u2014 Script
  scrA: "\ud835\udc9c",
  scrC: "\ud835\udc9e",
  scrE: "\u2130",
  scrF: "\u2131",
  scrI: "\u2110",
  scrJ: "\ud835\udca5",
  scrL: "\u2112",
  scrM: "\u2133",
  scrQ: "\ud835\udcac",
  scrR: "\u211b",
  scrS: "\ud835\udcae",
  scrT: "\ud835\udcaf",
  scrU: "\ud835\udcb0",
  scrb: "\ud835\udcb7",
  scrh: "\ud835\udcbd",
  scrl: "\ud835\udcc1",
  // Italic / Bold capitals
  italU: "\ud835\udc48",
  blC: "\ud835\udc02",
  blJ: "\ud835\udc09",
  blU: "\ud835\udc14",
  blb: "\ud835\udc1b",
  bly: "\ud835\udc32",
  // Music symbols
  semibr: "\ud834\udd5d",
  crotchet: "\u2669",
  quaver: "\u266a",
  squaver: "\u266c",
  sqquav: "\u266c",
  versicle1: "\u2123",
  versicle2: "\u211f",
  comtime: "\ud834\udd34",
  segno: "\ud834\udd0b",
  // Math / set
  Summ: "\u2211",
  Integ: "\u222b",
  conj: "\u260c",
  // Currency / letters
  Naira: "\u20a6",
  Asg: "\ua77d",
  // Combining-mark aliases (the "no-font" variants in OED.EXE)
  nfacu: "\u0301",
  nfasper: "\u0314",
  nfbreve: "\u0306",
  nfced: "\u0327",
  nfcirc: "\u0302",
  nffrown: "\u0311",
  nfgra: "\u0300",
  nfhacek: "\u030c",
  nfmac: "\u0304",
  nftilde: "\u0303",
  nfuml: "\u0308",
  // Brackets / shapes
  lhalfbr: "\u231c",
  rhalfbr: "\u231d",
  lhshoe: "\u2283",
  rhshoe: "\u2282",
  bigobl: "/",
  blozenge: "\u25c6",
  bsquare: "\u25a0",
  // Old English / runic
  runwyn: "\u16b9",
  runash: "\u16ab",
  // Misc
  tittle: "\u00b7",
  tie: "\u203f",
  // Ligatures (Latin typography)
  ffilig: "\ufb03",
  ffllig: "\ufb04",
  fllig: "\ufb02",
  ifilig: "\ufb01",
  ifflig: "\ufb00",
  istlig: "\ufb06",
  stlig: "\ufb06",
  ctlig: "ct",
  // Dotless letters
  dlessi: "\u0131",
  dlessj1: "\u0237",
  dlessj2: "\u0237",
  dlessj3: "\u0237",
  // Reversed / IPA letters
  revC: "\u2183",
  reva: "\u0250",
  revc: "\u0254",
  revv: "\u028c",
  revr: "\u0279",
  revope: "\u0258",
  revsc: "\u0281",
  ibar: "\u0268",
  ng: "\u014b",
  ope: "\u025b",
  lm: "\u02d0",
  // More math / typographic symbols
  fact: "!",
  minpl: "\u2213",
  planck: "\u210e",
  phi2: "\u03d5",
  pmil: "\u2030",
  sup2: "\u00b2",
  cprt: "\u00a9",
  // Old Latin / Egyptian Greek paleography
  elatS: "S",
  elatc1: "C",
  elatc2: "c",
  elatg1: "g",
  elatg2: "g",
  egy3: "\u03c5",
  egyasper: "\u1f51",
  // More Fraktur
  frE: "\ud835\udd08",
  frL: "\ud835\udd0f",
  frR: "\u211c",
  // Phoenician / Aramaic shapes \u2014 render as the Hebrew equivalent for legibility
  semain1: "\u05e2",
  semain2: "\u05e2",
  semhe: "\u05d4",
  semheth: "\u05d7",
  semkaph: "\u05db",
  semlamed1: "\u05dc",
  semlamed2: "\u05dc",
  semmem: "\u05de",
  semnun: "\u05e0",
  sempe: "\u05e4",
  semqoph1: "\u05e7",
  semqoph2: "\u05e7",
  semqoph3: "\u05e7",
  semresh: "\u05e8",
  semtav1: "\u05ea",
  semtav2: "\u05ea",
  semtav3: "\u05ea",
  semtav4: "\u05ea",
  semyod: "\u05d9",
  semzayin1: "\u05d6",
  semzayin2: "\u05d6",
  semzayin3: "\u05d6",
  // Arabic "full" variants \u2014 fall back to the base letter
  arainfull: "\u0639",
  arnunfull: "\u0646",
  arshinfull: "\u0634",
  arDadfull: "\u0636",
  artafull: "\u062a",
  aryafull: "\u064a",
  // Underdot transliteration diacritics (used for Sanskrit, Semitic etc.)
  udA: "\u1ea0",
  uda: "\u1ea1",
  udT: "\u1e6c",
  udh: "\u1e25",
  udw: "\u1e89",
  // Letters with bar / stroke
  bbar: "\u0180",
  dbar: "\u0111",
  ubar: "\u016b",
  pbar: "p\u0304",
  thbar: "\u00fe\u0304",
  // Devanagari (most common)
  devdh: "\u0927",
  devph: "\u092b",
  devt: "\u0924",
  devth: "\u0925",
  // Music ornaments / older notation
  mord: "\ud834\udd9d",
  longmord: "\ud834\udd9d",
  sqbreve: "\ud834\udd5c",
  oldsemibr1: "\ud834\udd5d",
  oldsemibr2: "\ud834\udd5d",
  oldbeta: "\u03b2",
  duplong1: "\ud834\udd5c",
  duplong2: "\ud834\udd5c",
  // Misc
  sigmatau: "\u03c3\u03c4",
  zh: "\u017e",
  ye: "y\u1d49",
  yt: "y\u1d57",
  reg: "\u00ae",
  per: "\u2044",
  half: "\u00bd",
  hgz: "\u0292",
  // Triangle / shape variants
  sidetri: "\u25b7",
  trli: "\u25b9",
  udtr: "\u2207",
  udqm: "\u00bf",
  // More math / set
  angle: "\u2220",
  intsec: "\u2229",
  wavyeq: "\u2248",
  ltappr: "\u2a85",
  ltflat: "\u2a95",
  // Astrological extras
  descnode: "\u260b",
  // Uncial / palaeographic letter forms \u2014 fall back to the modern letter
  uncU: "U",
  huncU: "U",
  // Triangle/box variants \u2014 use closest Unicode
  bigobl2: "/",
  // OED transliteration: literal short forms
  p: "p",
  pa: "pa",
  sh: "\u0161",
  // Chemistry bond markers (used in molecular formulas like -C(NH)OR, =NH, X\u2261Y)
  b1: "-",
  b2: "=",
  b3: "\u2261",
  // OED short-vowel / scansion marks (sht* = "short")
  shti: "\u026a",
  shtu: "\u028a",
  shtsyll: "\u02d8",
  shtlong1: "\u23d3",
  shtlong2: "\u23d2",
  // Confirmed via article context
  astm: "\u2042",
  oeamp: "\u204a",
  fata: "\u064e",
  semE: "\u2203",
  opp: "\u260d",
  Chirho: "\u2627",
  albrtime: "\ud834\udd35",
  pauseo: "\ud834\udd10",
  pauseu: "\ud834\udd11",
  Bantuo: "\u0186",
  bantuo: "\u0254",
  supgt: "\u02c3",
  suplt: "\u02c2",
  btril: "\u25c1",
  btrir: "\u25b7",
  Nplus: "N\u207a",
  vinc: "\u203e",
  sur: "\u02b3",
  frbl: "\u032d",
  thinqm: "\ufe56",
  // Chemistry bond strokes \u2014 bt* = top-half, bb* = bottom-half;
  // r = right-leaning (/), l = left-leaning (\), c = center (vertical |)
  btr1: "\u2571",
  btr2: "\u2571",
  bbr1: "\u2572",
  bbr2: "\u2572",
  btl1: "\u2572",
  bbl1: "\u2571",
  btc1: "\u2502",
  btc2: "\u2502",
  bbc1: "\u2502",
  bbc2: "\u2502",
  // Fractions \u2014 most common ones; OED uses <num>on<den>(th)? for any other fraction
  // (handled generically in entityPreview below).
  "3on4": "\u00be",
  "1on4": "\u00bc",
  "1on2": "\u00bd",
  // Generic table separator (the renderer rewrites this to a cell break inside <table>)
  tab: "\t",
  // Multiple primes (used to label substituent positions in chemical formulas)
  ppp: "\u2034",
  // Big-bracket family used to enclose stacked structural pairs in formulas
  obigb: "{",
  cbigb: "}",
  obigpren: "(",
  cbigpren: ")",
  obigsb: "[",
  cbigsb: "]",
  ob: "{",
  cb: "}",
  oab: "\u27e8",
  cab: "\u27e9",
  bra: "\u27e8",
  odsb: "\u27e6",
  cdsb: "\u27e7",
};

const PHONETIC_MULTI_REPLACEMENTS = [
  ["&bs", "\u00e6bs"],
  ["@U", "\u0259\u028a"],
  ["i:", "i\u02d0"],
  ["u:", "u\u02d0"],
  ["A:", "\u0251\u02d0"],
  ["O:", "\u0254\u02d0"],
  ["3:", "\u025c\u02d0"],
];

const PHONETIC_CHAR_REPLACEMENTS = {
  "\"": "\u02c8",
  "'": "\u02cc",
  "%": "\u02cc",
  "&": "\u00e6",
  "@": "\u0259",
  I: "\u026a",
  U: "\u028a",
  E: "\u025b",
  A: "\u0251",
  O: "\u0252",
  V: "\u028c",
  N: "\u014b",
  S: "\u0283",
  Z: "\u0292",
  T: "\u03b8",
  D: "\u00f0",
};

const GREEK_CHAR_REPLACEMENTS = {
  A: "\u0391",
  B: "\u0392",
  G: "\u0393",
  D: "\u0394",
  E: "\u0395",
  Z: "\u0396",
  H: "\u0397",
  Q: "\u0398",
  I: "\u0399",
  K: "\u039a",
  L: "\u039b",
  M: "\u039c",
  N: "\u039d",
  C: "\u039e",
  O: "\u039f",
  P: "\u03a0",
  R: "\u03a1",
  S: "\u03a3",
  T: "\u03a4",
  U: "\u03a5",
  F: "\u03a6",
  X: "\u03a7",
  Y: "\u03a8",
  W: "\u03a9",
  a: "\u03b1",
  b: "\u03b2",
  g: "\u03b3",
  d: "\u03b4",
  e: "\u03b5",
  z: "\u03b6",
  h: "\u03b7",
  q: "\u03b8",
  i: "\u03b9",
  k: "\u03ba",
  l: "\u03bb",
  m: "\u03bc",
  n: "\u03bd",
  c: "\u03be",
  o: "\u03bf",
  p: "\u03c0",
  r: "\u03c1",
  s: "\u03c3",
  j: "\u03c2",
  t: "\u03c4",
  u: "\u03c5",
  f: "\u03c6",
  x: "\u03c7",
  y: "\u03c8",
  w: "\u03c9",
};

const GREEK_ENTITY_BASES = {
  A: "\u0391",
  E: "\u0395",
  H: "\u0397",
  I: "\u0399",
  O: "\u039f",
  R: "\u03a1",
  U: "\u03a5",
  W: "\u03a9",
  a: "\u03b1",
  e: "\u03b5",
  h: "\u03b7",
  i: "\u03b9",
  o: "\u03bf",
  r: "\u03c1",
  u: "\u03c5",
  w: "\u03c9",
};

const GREEK_ENTITY_SUFFIX_MARKS = {
  acu: "\u0301",
  grave: "\u0300",
  frown: "\u0342",
  mac: "\u0304",
  breve: "\u0306",
  uml: "\u0308",
  lenis: "\u0313",
  asper: "\u0314",
};

const GREEK_STANDALONE_ENTITIES = {
  acu: "\u0301",
  grave: "\u0300",
  frown: "\u0342",
  lenis: "\u0313",
  asper: "\u0314",
  isub: "\u0345",
};

const STYLE_TAGS = new Set([
  "hw", "hm", "ph", "ps", "cf", "vf", "vd", "ve", "vfl", "la", "il",
  "bl", "pt", "q", "qt", "qd", "a", "w", "bib", "lc", "x", "xr", "sub",
  "xs", "xid", "gr", "gk", "i", "b", "in", "su", "pi", "nu", "dn", "fr",
]);

const WRAPPED_STYLE_TAGS = new Set([
  "hw", "hm", "ph", "ps", "cf", "vf", "vd", "ve", "vfl", "la", "il",
  "bl", "pt", "q", "qd", "a", "w", "x", "sub", "xs", "xid", "gr", "gk",
  "i", "b", "in", "su", "pi", "nu", "dn", "fr",
]);

const WORD_LIST_CODE_LABELS = {
  "4a": "n.",
  "4b": "n. 1",
  "4c": "n. 2",
  "4d": "n. 3",
  "7a": "vbl. n.",
  ":a": "a.",
  ">a": "v.",
  "Xa": "n.",
};

export class HttpRangeSource {
  constructor(url, baseOffset = 0) {
    this.url = url;
    this.baseOffset = baseOffset;
    this.size = null;
  }

  async read(offset, length) {
    if (length <= 0) return new Uint8Array();
    const start = offset + this.baseOffset;
    const end = start + length - 1;
    const response = await fetch(this.url, {
      headers: { Range: `bytes=${start}-${end}` },
    });
    if (response.status !== 206) {
      throw new Error(
        `Static host did not honor Range for ${this.url} ` +
          `(status ${response.status}). Use a range-capable server or choose a local file.`,
      );
    }
    const range = response.headers.get("content-range");
    if (range) {
      const match = range.match(/\/(\d+)$/);
      if (match) this.size = Number(match[1]) - this.baseOffset;
    }
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength !== length) {
      throw new Error(`Short range read at 0x${offset.toString(16)}`);
    }
    return new Uint8Array(buffer);
  }
}

export class BlobRangeSource {
  constructor(file) {
    this.file = file;
    this.size = file.size;
  }

  async read(offset, length) {
    if (length <= 0) return new Uint8Array();
    const buffer = await this.file.slice(offset, offset + length).arrayBuffer();
    if (buffer.byteLength !== length) {
      throw new Error(`Short file read at 0x${offset.toString(16)}`);
    }
    return new Uint8Array(buffer);
  }
}

function view(bytes) {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}

function u16be(bytes, offset) {
  return view(bytes).getUint16(offset, false);
}

function u32be(bytes, offset) {
  return view(bytes).getUint32(offset, false);
}

function i32be(bytes, offset) {
  return view(bytes).getInt32(offset, false);
}

function compareBytes(left, right) {
  const size = Math.min(left.length, right.length);
  for (let i = 0; i < size; i += 1) {
    if (left[i] !== right[i]) return left[i] - right[i];
  }
  return left.length - right.length;
}

function bytesStartsWith(value, prefix) {
  if (prefix.length > value.length) return false;
  for (let i = 0; i < prefix.length; i += 1) {
    if (value[i] !== prefix[i]) return false;
  }
  return true;
}

function highbitNormalizedByte(byte) {
  return byte >= 0x80 ? byte & 0x7f : byte;
}

function bytesToText(bytes) {
  let out = "";
  for (let i = 0; i < bytes.length; i += 1) {
    const byte = highbitNormalizedByte(bytes[i]);
    if (byte === 9 || byte === 10 || byte === 13 || (byte >= 32 && byte < 127)) {
      out += String.fromCharCode(byte);
    } else {
      out += ".";
    }
  }
  return out;
}

function concatBytes(parts) {
  const size = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(size);
  let pos = 0;
  for (const part of parts) {
    out.set(part, pos);
    pos += part.length;
  }
  return out;
}

function latin1Bytes(text) {
  const out = [];
  for (const ch of text) {
    const code = ch.codePointAt(0);
    out.push(code !== undefined && code <= 0xff ? code : 0x3f);
  }
  return Uint8Array.from(out);
}

function parseNulFragments(area) {
  const fragments = [];
  let pos = 0;
  while (pos < area.length) {
    const end = area.indexOf(0, pos);
    if (end < 0 || end === pos) break;
    fragments.push(area.subarray(pos, end));
    pos = end + 1;
  }
  while (fragments.length < 256) fragments.push(new Uint8Array());
  return fragments.slice(0, 256);
}

function parseLfMarkers(area, count) {
  const markers = [];
  let pos = 0;
  while (pos < area.length && markers.length < count) {
    const end = area.indexOf(0x0a, pos);
    if (end < 0) break;
    markers.push(area.subarray(pos, end));
    pos = end + 1;
  }
  while (markers.length < count) markers.push(new Uint8Array());
  return markers.slice(0, count);
}

function compareEntityToken(left, right) {
  let pos = 0;
  for (;;) {
    const lb = pos < left.length ? left[pos] : 0;
    const rb = pos < right.length ? right[pos] : 0;
    if (lb !== rb) return lb - rb;
    if (lb === 0x2e) return 0;
    pos += 1;
  }
}

function tableaExeCharClass(byte) {
  if (byte >= 0x41 && byte <= 0x5a) return 0x01;
  if (byte >= 0x61 && byte <= 0x7a) return 0x02;
  if (byte >= 0x30 && byte <= 0x39) return 0x84;
  if (byte === 0x09 || byte === 0x0a || byte === 0x0d || byte === 0x28 || byte === 0x29) return 0x28;
  if (byte === 0x20) return 0x48;
  if (byte >= 0x20 && byte < 0x7f) return 0x10;
  return 0x00;
}

function parseTableA(raw) {
  const recordCount = u16be(raw, 0);
  const entityCount = u16be(raw, 2);
  const offsetCount = u16be(raw, 4);
  const poolSize = u16be(raw, 6);
  if (offsetCount !== recordCount * 3) {
    throw new Error(`Unexpected Table-A offset count ${offsetCount}`);
  }

  const offsetsAt = 8;
  const offsets = [];
  for (let i = 0; i < offsetCount + 1; i += 1) {
    offsets.push(u16be(raw, offsetsAt + i * 2));
  }

  const indexAt = offsetsAt + (offsetCount + 1) * 2;
  const indexCount = entityCount + 0x100;
  const indexMap = [];
  for (let i = 0; i < indexCount; i += 1) {
    indexMap.push(u16be(raw, indexAt + i * 2));
  }

  const poolAt = indexAt + indexCount * 2;
  const pool = raw.subarray(poolAt, poolAt + poolSize);
  if (pool.length !== poolSize) throw new Error("Short Table-A pool");

  return { recordCount, entityCount, offsets, indexMap, pool };
}

function tableaRecord(table, index) {
  if (index < 0 || index >= table.recordCount) throw new Error(`Table-A record out of range: ${index}`);
  const pos = index * 3;
  const a = table.offsets[pos];
  const b = table.offsets[pos + 1];
  const c = table.offsets[pos + 2];
  const d = table.offsets[pos + 3];
  return {
    source: table.pool.subarray(a, b),
    primary: table.pool.subarray(b, c),
    secondary: table.pool.subarray(c, d),
  };
}

function tableaDirectRecordIndex(table, byte) {
  const value = table.indexMap[byte];
  return value === 0xffff || value === undefined ? null : value;
}

function tableaFindEntityRecordIndex(table, token) {
  let lo = 0x100;
  let hi = 0x100 + table.entityCount;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    const recordIndex = table.indexMap[mid];
    const record = tableaRecord(table, recordIndex);
    const cmp = compareEntityToken(token, record.source);
    if (cmp < 0) hi = mid;
    else if (cmp > 0) lo = mid + 1;
    else return recordIndex;
  }
  return null;
}

function tableaFindEntityAndDot(table, data, pos) {
  const dot = data.indexOf(0x2e, pos + 1);
  if (dot < 0) return { recordIndex: null, dot: data.length };
  return {
    recordIndex: tableaFindEntityRecordIndex(table, data.subarray(pos, dot + 1)),
    dot,
  };
}

function appendBytes(out, bytes) {
  for (const byte of bytes) out.push(byte);
}

function encodeTableAExe(table, text, mode = 0x0100, modeHi = 0) {
  const data = latin1Bytes(text);
  const primary = [];
  const secondary = [];
  let pos = 0;
  const lowerMarker = 0x03;
  const upperMarker = 0x02;

  if (mode === 0x0100 && modeHi === 0 && data.length) {
    secondary.push(data[0]);
    pos = 1;
    if (pos < data.length) {
      secondary.push(data[pos]);
      pos += 1;
    }
  }

  while (pos < data.length && data[pos] !== 0) {
    const byte = data[pos];

    if (byte === 0x28 || byte === 0x3c) {
      let balancedParen = false;
      if (byte === 0x28) {
        balancedParen = data.indexOf(0x29, pos + 1) >= 0;
      }
      if (!balancedParen) {
        while (pos < data.length && data[pos] !== 0) {
          const current = data[pos];
          let recordIndex = null;
          if (current === 0x26) {
            const found = tableaFindEntityAndDot(table, data, pos);
            recordIndex = found.recordIndex;
            pos = found.dot;
          } else {
            recordIndex = tableaDirectRecordIndex(table, current);
          }
          if (recordIndex !== null) appendBytes(secondary, tableaRecord(table, recordIndex).secondary);
          if (pos >= data.length || data[pos] === 0) break;
          pos += 1;
        }
        continue;
      }
    }

    if (byte === 0x26) {
      const found = tableaFindEntityAndDot(table, data, pos);
      pos = found.dot;
      if (found.recordIndex !== null) {
        const record = tableaRecord(table, found.recordIndex);
        appendBytes(primary, record.primary);
        appendBytes(secondary, record.secondary);
      }
      if (pos >= data.length || data[pos] === 0) continue;
      pos += 1;
      continue;
    }

    const cls = tableaExeCharClass(byte);
    if ((cls & 0x03) && !((mode === 0x0103 || mode === 0x0104) && modeHi === 0)) {
      if (cls & 0x01) {
        primary.push(byte);
        secondary.push(upperMarker);
      } else {
        primary.push((byte - 0x20) & 0xff);
        secondary.push(lowerMarker);
      }
      pos += 1;
      continue;
    }

    const recordIndex = tableaDirectRecordIndex(table, byte);
    if (recordIndex !== null) {
      const record = tableaRecord(table, recordIndex);
      appendBytes(primary, record.primary);
      appendBytes(secondary, record.secondary);
    }
    pos += 1;
  }

  primary.push(lowerMarker);
  appendBytes(primary, secondary);
  return Uint8Array.from(primary);
}

function tableaPrimaryPrefix(encoded) {
  let end = 0;
  while (end < encoded.length && encoded[end] > 0x03) end += 1;
  return encoded.subarray(0, end);
}

function tableaRankCodeValue(first, second) {
  const one = (byte) => ((tableaExeCharClass(byte) & 0x02) ? byte - 0x57 : byte - 0x30);
  return 36 * one(first) + one(second);
}

function decodeTableAExe(table, encoded, mode = 0x0100, modeHi = 0) {
  const separator = 0x03;
  const upperMarker = 0x02;
  const split = encoded.indexOf(separator);
  if (split < 0) {
    const end = encoded.indexOf(0);
    return end < 0 ? encoded : encoded.subarray(0, end);
  }

  let primaryPos = 0;
  let secondaryPos = split;
  const out = [];

  if (mode === 0x0100 && modeHi === 0) {
    if (secondaryPos + 1 < encoded.length) out.push(encoded[secondaryPos + 1]);
    if (secondaryPos + 2 < encoded.length) out.push(encoded[secondaryPos + 2]);
    secondaryPos += 2;
  }

  while (secondaryPos < encoded.length && encoded[secondaryPos] !== 0) {
    secondaryPos += 1;
    if (secondaryPos >= encoded.length) break;
    const marker = encoded[secondaryPos];

    if (marker === separator || marker === 0) {
      if (primaryPos < split) {
        out.push((encoded[primaryPos] + 0x20) & 0xff);
        primaryPos += 1;
      }
      if (marker === 0) break;
      continue;
    }

    if (marker === upperMarker) {
      if (primaryPos < split) {
        out.push(encoded[primaryPos]);
        primaryPos += 1;
      }
      continue;
    }

    if (secondaryPos + 1 >= encoded.length) break;
    const recordIndex = tableaRankCodeValue(encoded[secondaryPos], encoded[secondaryPos + 1]);
    secondaryPos += 1;
    if (recordIndex >= 0 && recordIndex < table.recordCount) {
      const record = tableaRecord(table, recordIndex);
      appendBytes(out, record.source);
      primaryPos = Math.min(split, primaryPos + record.primary.length);
    }
  }

  while (primaryPos < split) {
    out.push(encoded[primaryPos]);
    primaryPos += 1;
  }
  return Uint8Array.from(out);
}

function latin1Text(bytes) {
  let out = "";
  for (const byte of bytes) {
    if (byte === 0) break;
    out += String.fromCharCode(byte);
  }
  return out;
}

function renderListKeyText(text) {
  let out = text
    .replace(/&[A-Za-z0-9]+\.?/g, (token) => entityPreview(token))
    .replace(/['\u2019]/g, "\u2019")
    .replace(/\s+/g, " ")
    .trim();
  let unmatched = 0;
  for (const ch of out) {
    if (ch === "(") unmatched += 1;
    else if (ch === ")" && unmatched > 0) unmatched -= 1;
  }
  if (unmatched > 0) out += ")".repeat(unmatched);
  return out;
}

function wordListKeyLabel(table, encodedKey) {
  const decoded = latin1Text(decodeTableAExe(table, encodedKey));
  const withoutHiddenPrefix = decoded.length >= 2 ? decoded.slice(2) : decoded;
  return renderListKeyText(withoutHiddenPrefix);
}

function wordListKeyCode(encodedKey) {
  const split = encodedKey.indexOf(0x03);
  if (split < 0 || split + 2 >= encodedKey.length) return "";
  return String.fromCharCode(encodedKey[split + 1], encodedKey[split + 2]);
}

function wordListKeyAnnotation(encodedKey) {
  return WORD_LIST_CODE_LABELS[wordListKeyCode(encodedKey)] ?? "";
}

function isEntryStartRecord(data) {
  if (data.length < 2) return false;
  if (highbitNormalizedByte(data[0]) !== 0x3c) return false;
  if (highbitNormalizedByte(data[1]) !== 0x65) return false;
  if (data.length === 2) return true;
  const next = highbitNormalizedByte(data[2]);
  return next === 0x3e || next === 0x20 || next === 0x09 || next === 0x0a;
}

function buildCanonicalDecodeTable(lengthCounts) {
  let code = 0;
  let symbol = 0;
  const tables = Array.from({ length: lengthCounts.length + 1 }, () => new Map());
  for (let bits = 1; bits <= lengthCounts.length; bits += 1) {
    const count = lengthCounts[bits - 1];
    for (let i = 0; i < count; i += 1) {
      tables[bits].set(code, symbol);
      symbol += 1;
      code += 1;
    }
    code <<= 1;
  }
  return tables;
}

class CanonicalBitDecoder {
  constructor(data, lengthCounts, bitOffset = 0, endBit = null) {
    this.data = data;
    this.table = buildCanonicalDecodeTable(lengthCounts);
    this.maxBits = lengthCounts.length;
    this.bitOffset = bitOffset;
    this.endBit = Math.min(endBit ?? data.length * 8, data.length * 8);
  }

  seek(bitOffset) {
    if (bitOffset < 0 || bitOffset > this.endBit) {
      throw new Error(`Bit offset out of range: ${bitOffset}`);
    }
    this.bitOffset = bitOffset;
  }

  nextSymbol() {
    let acc = 0;
    for (let bits = 1; bits <= this.maxBits; bits += 1) {
      if (this.bitOffset >= this.endBit) return -1;
      const byte = this.data[this.bitOffset >> 3];
      const shift = 7 - (this.bitOffset & 7);
      acc = (acc << 1) | ((byte >> shift) & 1);
      this.bitOffset += 1;
      const symbol = this.table[bits].get(acc);
      if (symbol !== undefined) return symbol;
    }
    return -1;
  }
}

class BodyBlockDecoder {
  constructor(codec) {
    this.codec = codec;
    this.block = codec.block;
    this.decoder = new CanonicalBitDecoder(codec.compressed, codec.lengthCounts);
    this.seekState = null;
    this.currentLogical = this.block.logicalOffset;
    this.symbolsSinceWindowStart = 0;
  }

  seek(logicalOffset) {
    const blockEnd = this.block.logicalOffset + this.block.logicalLength;
    if (logicalOffset < this.block.logicalOffset || logicalOffset >= blockEnd) {
      throw new Error(`Logical offset 0x${logicalOffset.toString(16)} outside block ${this.block.index}`);
    }
    const rel = logicalOffset - this.block.logicalOffset;
    const window = Math.floor(rel / this.codec.windowSpan);
    const bitStart = this.codec.prefixValues[window];
    this.decoder.seek(bitStart);
    const windowStart = this.block.logicalOffset + window * this.codec.windowSpan;
    let current = windowStart;
    let skipped = 0;
    while (current < logicalOffset) {
      const symbol = this.decoder.nextSymbol();
      if (symbol < 0) throw new Error(`Ran out of aux symbols before 0x${logicalOffset.toString(16)}`);
      skipped += 1;
      if (symbol === this.codec.sentinelSymbol) current += 1;
    }
    this.seekState = { window, windowStart, bitStart };
    this.currentLogical = logicalOffset;
    this.symbolsSinceWindowStart = skipped;
  }

  nextRecord(maxFragments = 8192) {
    if (this.seekState === null) this.seek(this.block.logicalOffset);
    const out = [];
    const fragmentIds = [];
    let terminated = false;
    for (let i = 0; i < maxFragments; i += 1) {
      const symbol = this.decoder.nextSymbol();
      if (symbol < 0) break;
      this.symbolsSinceWindowStart += 1;
      if (symbol === this.codec.sentinelSymbol) {
        terminated = true;
        break;
      }
      if (symbol < 0 || symbol >= this.codec.fragmentOffsets.length - 1) {
        throw new Error(`Invalid fragment id ${symbol} in block ${this.block.index}`);
      }
      const lo = this.codec.fragmentOffsets[symbol];
      const hi = this.codec.fragmentOffsets[symbol + 1];
      out.push(this.codec.payload.subarray(lo, hi));
      fragmentIds.push(symbol);
    }
    const record = {
      logicalOffset: this.currentLogical,
      block: this.block,
      data: concatBytes(out),
      fragmentIds,
      terminated,
    };
    this.currentLogical += 1;
    return record;
  }
}

export class OED2Reader {
  constructor(source) {
    this.source = source;
    this.bodyControl = null;
    this.bodyBlocks = new Map();
    this.blockCodecs = new Map();
    this.lists = new Map();
    this.tableAs = new Map();
    this.listBlocks = new Map();
    this.pointerCache = new Map();
    this.headgroupCache = new Map();
    this.entryStartCache = new Map();
  }

  async readBodyControl() {
    if (this.bodyControl) return this.bodyControl;
    const bytes = await this.source.read(BODY_CONTROL_OFFSET, BODY_CONTROL_WORDS * 4);
    const words = [];
    for (let i = 0; i < BODY_CONTROL_WORDS; i += 1) {
      words.push(u32be(bytes, i * 4));
    }
    this.bodyControl = {
      offset: BODY_CONTROL_OFFSET,
      magicOrChecksum: words[0],
      stride: words[1],
      blockCount: words[2],
      logicalTotal: words[3],
      logicalBlockSize: words[4],
      auxClassCount: words[5],
      repeatedStride: words[6],
      tailOrIndexBytes: words[7],
      prefixWordBytes: words[8],
      firstBlockOffset: BODY_CONTROL_OFFSET + words[1],
    };
    return this.bodyControl;
  }

  async readBodyBlock(index) {
    if (this.bodyBlocks.has(index)) return this.bodyBlocks.get(index);
    const control = await this.readBodyControl();
    if (index < 0 || index >= control.blockCount) {
      throw new Error(`Body block index out of range: ${index}`);
    }
    const fileOffset = control.firstBlockOffset + index * control.stride;
    const bytes = await this.source.read(fileOffset, BODY_HEADER_BYTES);
    const logicalOffset = u32be(bytes, 0);
    const logicalLength = u32be(bytes, 4);
    const storedLength = u32be(bytes, 8);
    const auxCount = u32be(bytes, 12);
    const block = {
      index,
      fileOffset,
      logicalOffset,
      logicalLength,
      storedLength,
      auxCount,
      payloadOffset: fileOffset + BODY_HEADER_BYTES,
      payloadEnd: fileOffset + BODY_HEADER_BYTES + storedLength,
      auxControlOffset: fileOffset + BODY_HEADER_BYTES + storedLength,
      auxStreamOffset: fileOffset + BODY_HEADER_BYTES + storedLength + 0x80,
    };
    this.bodyBlocks.set(index, block);
    return block;
  }

  async blockForLogicalOffset(logicalOffset) {
    const control = await this.readBodyControl();
    let index = Math.floor(logicalOffset / control.logicalBlockSize);
    index = Math.max(0, Math.min(control.blockCount - 1, index));
    for (let guard = 0; guard < 8; guard += 1) {
      const block = await this.readBodyBlock(index);
      if (logicalOffset < block.logicalOffset) {
        index -= 1;
      } else if (logicalOffset >= block.logicalOffset + block.logicalLength) {
        index += 1;
      } else {
        return block;
      }
      if (index < 0 || index >= control.blockCount) break;
    }
    throw new Error(`No body block for logical offset 0x${logicalOffset.toString(16)}`);
  }

  async readOedList(name = "word") {
    if (this.lists.has(name)) return this.lists.get(name);
    const spec = OED_LISTS[name];
    if (!spec) throw new Error(`Unknown OED list ${name}`);
    const header = await this.source.read(spec.control, 14);
    const blockCount = u16be(header, 4);
    const list = {
      name,
      controlOffset: spec.control,
      tableB: spec.tableB,
      magic: u16be(header, 0),
      version: u16be(header, 2),
      blockCount,
      blockSize: u16be(header, 6),
      maxKeyBytes: u16be(header, 8),
      fragmentBytes: u16be(header, 10),
      markerBytes: u16be(header, 12),
      blockDataOffset: 0,
      fragments: [],
      cumulativeDeltas: [],
      countBase: 0,
      firstFragmentSkip: new Uint8Array(),
      markers: [],
      blockStarts: [],
      totalEntries: 0,
    };
    const restSize = list.fragmentBytes + 4 + blockCount * 4 + blockCount + list.markerBytes;
    const rest = await this.source.read(spec.control + 14, restSize);
    const fragmentArea = rest.subarray(0, list.fragmentBytes);
    list.fragments = parseNulFragments(fragmentArea);
    list.countBase = u32be(rest, list.fragmentBytes);
    const deltasAt = list.fragmentBytes + 4;
    for (let i = 0; i < blockCount; i += 1) {
      list.cumulativeDeltas.push(i32be(rest, deltasAt + i * 4));
    }
    const skipsAt = deltasAt + blockCount * 4;
    list.firstFragmentSkip = rest.subarray(skipsAt, skipsAt + blockCount);
    const markersAt = skipsAt + blockCount;
    list.markers = parseLfMarkers(rest.subarray(markersAt, markersAt + list.markerBytes), blockCount);
    list.blockDataOffset = spec.control + list.version * list.blockSize;
    list.entriesInBlock = (index) => {
      if (index === 0) return list.cumulativeDeltas[0];
      return list.cumulativeDeltas[index] - list.cumulativeDeltas[index - 1] + list.countBase;
    };
    let totalEntries = 0;
    for (let i = 0; i < blockCount; i += 1) {
      list.blockStarts.push(totalEntries);
      totalEntries += list.entriesInBlock(i);
    }
    list.totalEntries = totalEntries;
    this.lists.set(name, list);
    return list;
  }

  async readTableA(name = "word") {
    if (this.tableAs.has(name)) return this.tableAs.get(name);
    const spec = OED_LISTS[name];
    if (!spec?.tableA) throw new Error(`No Table-A anchor for OED list ${name}`);
    const raw = await this.source.read(spec.tableA, 0x4000);
    const table = parseTableA(raw);
    this.tableAs.set(name, table);
    return table;
  }

  async decodeOedListBlock(list, index) {
    if (index < 0 || index >= list.blockCount) {
      throw new Error(`OED list block out of range: ${index}`);
    }
    const cacheKey = `${list.name}:${index}`;
    if (this.listBlocks.has(cacheKey)) return this.listBlocks.get(cacheKey);

    const count = list.entriesInBlock(index);
    const base = list.blockDataOffset + index * list.blockSize;
    const block = await this.source.read(base, list.blockSize);
    const nibbleBytes = Math.floor((count + 1) / 2);
    let fragPtr = nibbleBytes;
    if (fragPtr >= block.length) return [];

    let curFrag = list.fragments[block[fragPtr]] ?? new Uint8Array();
    fragPtr += 1;
    let curPos = list.firstFragmentSkip[index] ?? 0;
    let previous = Array.from(list.markers[index] ?? new Uint8Array());
    const entries = [];

    for (let i = 0; i < count; i += 1) {
      const sharedByte = block[i >> 1];
      const shared = (i & 1) === 0 ? sharedByte >> 4 : sharedByte & 0x0f;
      const current = previous.slice(0, shared);
      for (;;) {
        while (curPos >= curFrag.length) {
          if (fragPtr >= block.length) {
            const partial = Uint8Array.from(current);
            entries.push(partial);
            this.listBlocks.set(cacheKey, entries);
            return entries;
          }
          curFrag = list.fragments[block[fragPtr]] ?? new Uint8Array();
          fragPtr += 1;
          curPos = 0;
        }
        const byte = curFrag[curPos];
        curPos += 1;
        if (byte === 0x0a) break;
        current.push(byte);
      }
      entries.push(Uint8Array.from(current));
      previous = current;
    }

    this.listBlocks.set(cacheKey, entries);
    return entries;
  }

  async readPointerRecord(name, index) {
    const cacheKey = `${name}:${index}`;
    if (this.pointerCache.has(cacheKey)) return this.pointerCache.get(cacheKey);
    const list = await this.readOedList(name);
    const bytes = await this.source.read(list.tableB + index * 8, 8);
    const row = { left: u32be(bytes, 0), logical: u32be(bytes, 4) };
    this.pointerCache.set(cacheKey, row);
    return row;
  }

  async readBlockCodec(block) {
    if (this.blockCodecs.has(block.index)) return this.blockCodecs.get(block.index);
    const control = await this.readBodyControl();
    const frame = await this.source.read(block.fileOffset, control.stride);
    const payloadRaw = frame.subarray(BODY_HEADER_BYTES, BODY_HEADER_BYTES + block.storedLength);
    const payload = new Uint8Array(payloadRaw);
    const fragmentOffsets = [0];
    for (let i = 0; i < payload.length; i += 1) {
      if (payload[i] >= 0x80) {
        payload[i] &= 0x7f;
        fragmentOffsets.push(i + 1);
      }
    }
    const auxControlStart = BODY_HEADER_BYTES + block.storedLength;
    const auxControl = frame.subarray(auxControlStart, auxControlStart + 0x80);
    const n = u32be(auxControl, 0);
    const lengthCounts = [];
    for (let i = 0; i < n; i += 1) {
      lengthCounts.push(u32be(auxControl, 4 + i * 4));
    }
    const auxRaw = frame.subarray(auxControlStart + 0x80);
    const prefixValues = [];
    for (let i = 0; i < BODY_AUX_PREFIX_WORDS; i += 1) {
      prefixValues.push(u32be(auxRaw, i * 4));
    }
    const compressed = auxRaw.subarray(BODY_AUX_PREFIX_WORDS * 4);
    const sentinelDecoder = new CanonicalBitDecoder(compressed, lengthCounts);
    const sentinelSymbol = sentinelDecoder.nextSymbol();
    const codec = {
      block,
      payload,
      fragmentOffsets,
      lengthCounts,
      prefixValues,
      compressed,
      sentinelSymbol,
      windowSpan: Math.ceil(block.logicalLength / control.auxClassCount),
    };
    this.blockCodecs.set(block.index, codec);
    return codec;
  }

  async makeBlockDecoder(block) {
    return new BodyBlockDecoder(await this.readBlockCodec(block));
  }

  async findEntryStartNear(logicalOffset) {
    if (this.entryStartCache.has(logicalOffset)) return this.entryStartCache.get(logicalOffset);
    const block = await this.blockForLogicalOffset(logicalOffset);
    for (let index = block.index; index >= Math.max(0, block.index - 3); index -= 1) {
      const candidateBlock = await this.readBodyBlock(index);
      const decoder = await this.makeBlockDecoder(candidateBlock);
      decoder.seek(candidateBlock.logicalOffset);
      let latest = null;
      const blockEnd = candidateBlock.logicalOffset + candidateBlock.logicalLength;
      while (decoder.currentLogical < blockEnd && decoder.currentLogical <= logicalOffset) {
        const record = decoder.nextRecord();
        if (isEntryStartRecord(record.data)) latest = record.logicalOffset;
        if (!record.terminated) break;
      }
      if (latest !== null) {
        this.entryStartCache.set(logicalOffset, latest);
        return latest;
      }
    }
    this.entryStartCache.set(logicalOffset, logicalOffset);
    return logicalOffset;
  }

  async headgroupAtOrdinal(index) {
    if (this.headgroupCache.has(index)) return this.headgroupCache.get(index);
    const pointer = await this.readPointerRecord("word", index);
    const entryLogical = await this.findEntryStartNear(pointer.logical);
    const parts = [];
    let current = entryLogical;
    for (let i = 0; i < 160; i += 1) {
      const block = await this.blockForLogicalOffset(current);
      const decoder = await this.makeBlockDecoder(block);
      decoder.seek(current);
      const record = decoder.nextRecord();
      parts.push(record.data);
      if (bytesToText(record.data).includes("</hg>")) break;
      if (!record.terminated) break;
      current = record.logicalOffset + 1;
    }
    const data = concatBytes(parts);
    const label = sgmlHeadgroupText(data);
    const text = bytesToText(data);
    const hgEnd = text.indexOf("</hg>");
    const hgSource = hgEnd >= 0 ? text.slice(0, hgEnd) : text;
    const titleSpans = hgSource.match(/<(hw|hm|ps)>[\s\S]*?<\/\1>/g) ?? [];
    const labelHtml = renderSourceHtml(titleSpans.join(" "));
    const out = { index, label, labelHtml, logical: entryLogical, targetLogical: pointer.logical };
    this.headgroupCache.set(index, out);
    return out;
  }

  async decodeArticleAtOrdinal(index) {
    const pointer = await this.readPointerRecord("word", index);
    const entryLogical = await this.findEntryStartNear(pointer.logical);
    return this.decodeArticleAtLogical(entryLogical, index, pointer.logical);
  }

  async decodeArticleAtLogical(logicalOffset, index = null, targetLogical = null) {
    const parts = [];
    const records = [];
    let current = logicalOffset;
    let stopReason = "max-records";
    let endLogical = null;
    for (let count = 0; count < 12000; count += 1) {
      const block = await this.blockForLogicalOffset(current);
      const decoder = await this.makeBlockDecoder(block);
      decoder.seek(current);
      const blockEnd = block.logicalOffset + block.logicalLength;
      while (decoder.currentLogical < blockEnd && count < 12000) {
        const record = decoder.nextRecord();
        if (records.length > 0 && isEntryStartRecord(record.data)) {
          stopReason = "next-entry";
          endLogical = record.logicalOffset;
          return {
            index,
            logical: logicalOffset,
            targetLogical,
            endLogical,
            stopReason,
            recordCount: records.length,
            records,
            data: concatBytes(parts),
          };
        }
        records.push(record);
        parts.push(record.data);
        if (!record.terminated) {
          stopReason = "unterminated-record";
          endLogical = record.logicalOffset;
          return {
            index,
            logical: logicalOffset,
            targetLogical,
            endLogical,
            stopReason,
            recordCount: records.length,
            records,
            data: concatBytes(parts),
          };
        }
        current = record.logicalOffset + 1;
        count += 1;
      }
    }
    return {
      index,
      logical: logicalOffset,
      targetLogical,
      endLogical,
      stopReason,
      recordCount: records.length,
      records,
      data: concatBytes(parts),
    };
  }

  oedListMarkerBlock(list, key) {
    let selected = 0;
    let hi = list.blockCount - 1;
    while (hi > selected) {
      const mid = Math.floor((selected + hi + 1) / 2);
      const cmp = compareBytes(key, list.markers[mid]);
      if (cmp === 0) {
        hi = mid;
        selected = mid;
      } else if (cmp < 0) {
        hi = mid - 1;
      } else {
        selected = mid;
      }
    }
    return selected;
  }

  async wordPrimaryKey(query) {
    const table = await this.readTableA("word");
    const encoded = encodeTableAExe(table, `0a${query}`);
    return tableaPrimaryPrefix(encoded);
  }

  async lookup(query, limit = 40, onProbe = null) {
    const list = await this.readOedList("word");
    const table = await this.readTableA("word");
    const key = tableaPrimaryPrefix(encodeTableAExe(table, `0a${query}`));
    if (!key.length) return [];
    const markerBlock = this.oedListMarkerBlock(list, key);
    let blockIndex = markerBlock;
    let globalStart = list.blockStarts[blockIndex];
    let blocksRead = 0;
    let entriesScanned = 0;
    const raw = [];
    let done = false;
    const candidateCap = Math.max(Math.ceil(limit * 1.5), 32);

    while (blockIndex < list.blockCount && raw.length < candidateCap && !done) {
      const entries = await this.decodeOedListBlock(list, blockIndex);
      blocksRead += 1;
      onProbe?.({
        markerBlock,
        blockIndex,
        blocksRead,
        entriesScanned,
        marker: bytesToText(list.markers[blockIndex] ?? new Uint8Array()),
      });
      for (let localIndex = 0; localIndex < entries.length; localIndex += 1) {
        const entry = entries[localIndex];
        entriesScanned += 1;
        if (bytesStartsWith(entry, key)) {
          const index = globalStart + localIndex;
          const listLabel = wordListKeyLabel(table, entry);
          const annotation = wordListKeyAnnotation(entry);
          raw.push({ index, entry, listLabel, annotation });
          if (raw.length >= candidateCap) break;
        } else if (raw.length > 0 || compareBytes(entry, key) > 0) {
          done = true;
          break;
        }
      }
      globalStart += entries.length;
      blockIndex += 1;
    }
    onProbe?.({ markerBlock, blockIndex: blockIndex - 1, blocksRead, entriesScanned, done: true });

    const headgroups = await Promise.all(raw.map((c) => this.headgroupAtOrdinal(c.index)));

    const candidates = raw.map((c, i) => {
      const headgroup = headgroups[i];
      const headgroupKey = normalizeSearch(headgroup.label);
      const listKey = normalizeSearch(c.listLabel);
      const label = c.annotation || !headgroupKey.startsWith(listKey) ? c.listLabel : headgroup.label;
      return { ...headgroup, listLabel: c.listLabel, label, annotation: c.annotation, indexKey: c.entry };
    });

    const labelsWithPrimary = new Set();
    for (const c of candidates) {
      if (c.annotation || c.label !== c.listLabel) labelsWithPrimary.add(c.listLabel);
    }
    const seen = new Set();
    const filtered = [];
    for (const c of candidates) {
      const isPrimary = c.annotation || c.label !== c.listLabel;
      if (!isPrimary && labelsWithPrimary.has(c.listLabel)) continue;
      const dedupKey = `${c.listLabel}${c.label}${c.annotation}`;
      if (seen.has(dedupKey)) continue;
      seen.add(dedupKey);
      filtered.push(c);
      if (filtered.length >= limit) break;
    }
    return filtered;
  }
}

export function entityPreview(token) {
  let name = token.startsWith("&") ? token.slice(1) : token;
  if (name.endsWith(".")) name = name.slice(0, -1);
  if (Object.prototype.hasOwnProperty.call(ENTITY_NAME_UNICODE, name)) {
    return ENTITY_NAME_UNICODE[name];
  }
  const suffixes = Object.keys(ENTITY_SUFFIX_MARKS).sort((a, b) => b.length - a.length);
  const SUFFIX_BASES = { ae: "æ", Ae: "Æ", AE: "Æ", oe: "œ", Oe: "Œ", OE: "Œ" };
  for (const suffix of suffixes) {
    if (name.endsWith(suffix) && name.length > suffix.length) {
      const base = name.slice(0, -suffix.length);
      if (/^[A-Za-z]$/.test(base)) {
        return (base + ENTITY_SUFFIX_MARKS[suffix]).normalize("NFC");
      }
      if (Object.prototype.hasOwnProperty.call(SUFFIX_BASES, base)) {
        return (SUFFIX_BASES[base] + ENTITY_SUFFIX_MARKS[suffix]).normalize("NFC");
      }
    }
  }
  const greek = greekEntityPreview(token);
  if (greek !== null) return greek;
  const fraction = name.match(/^(\d+)on(\d+)(?:th)?$/);
  if (fraction) {
    const num = fraction[1];
    const den = fraction[2];
    const VULGAR = {
      "1/2": "½", "1/3": "⅓", "2/3": "⅔", "1/4": "¼", "3/4": "¾",
      "1/5": "⅕", "2/5": "⅖", "3/5": "⅗", "4/5": "⅘",
      "1/6": "⅙", "5/6": "⅚",
      "1/7": "⅐",
      "1/8": "⅛", "3/8": "⅜", "5/8": "⅝", "7/8": "⅞",
      "1/9": "⅑",
      "1/10": "⅒",
    };
    const key = `${num}/${den}`;
    return VULGAR[key] ?? `${num}⁄${den}`;
  }
  return `<${name}>`;
}

export function decodePhoneticText(text) {
  let out = text;
  for (const [source, replacement] of PHONETIC_MULTI_REPLACEMENTS) {
    out = out.replaceAll(source, replacement);
  }
  return Array.from(out, (ch) => PHONETIC_CHAR_REPLACEMENTS[ch] ?? ch).join("");
}

function decodeGreekText(text) {
  return Array.from(text, (ch) => GREEK_CHAR_REPLACEMENTS[ch] ?? ch).join("");
}

function greekEntityPreview(token) {
  const name = token.replace(/^&/, "").replace(/\.$/, "");
  if (Object.prototype.hasOwnProperty.call(GREEK_STANDALONE_ENTITIES, name)) {
    return GREEK_STANDALONE_ENTITIES[name];
  }

  const match = name.match(/^g?([AEHIORUWaehioruw])(acu|grave|frown|mac|breve|uml|lenis|asper)$/);
  if (!match) return null;

  const base = GREEK_ENTITY_BASES[match[1]];
  const mark = GREEK_ENTITY_SUFFIX_MARKS[match[2]];
  if (!base || !mark) return null;
  return (base + mark).normalize("NFC");
}

function tagName(tag) {
  let body = tag.slice(1, -1).trim().toLowerCase();
  const closing = body.startsWith("/");
  if (closing) body = body.slice(1).trimStart();
  if (body.endsWith("/")) body = body.slice(0, -1).trimEnd();
  const name = body.split(/\s+/, 1)[0] ?? "";
  return { name, closing };
}

export function sgmlHeadgroupText(data) {
  const source = bytesToText(data);
  const out = [];
  let inside = false;
  for (let pos = 0; pos < source.length;) {
    if (source.startsWith("</hg>", pos)) break;
    const ch = source[pos];
    if (ch === "<") {
      const end = source.indexOf(">", pos);
      if (end < 0) break;
      const tag = source.slice(pos, end + 1).toLowerCase();
      if (tag.startsWith("<hw") || tag.startsWith("<hm") || tag.startsWith("<ps")) {
        inside = true;
      } else if (tag.startsWith("</hw") || tag.startsWith("</hm") || tag.startsWith("</ps")) {
        if (out.length && out[out.length - 1] !== " ") out.push(" ");
        inside = false;
      }
      pos = end + 1;
      continue;
    }
    if (!inside) {
      pos += 1;
      continue;
    }
    if (ch === "&") {
      const match = source.slice(pos).match(/^&[A-Za-z0-9]+\.?/);
      if (match) {
        out.push(entityPreview(match[0]));
        pos += match[0].length;
        continue;
      }
    }
    if (ch === "'") out.push("\u2019");
    else if (/\s/.test(ch)) out.push(" ");
    else out.push(ch);
    pos += 1;
  }
  return out.join("").replace(/\s+/g, " ").trim();
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;");
}

function keepEdgePunctuationWithPreviousWord(out, text) {
  if (!/^[()[\]]/.test(text)) return;
  const last = out.length - 1;
  if (last >= 0 && out[last].endsWith(" ")) {
    out[last] = `${out[last].slice(0, -1)}\u00a0`;
  }
}

function protectInlinePunctuation(text) {
  return text
    .replace(/ ([([])/g, "\u00a0$1")
    .replace(/([([])/g, "$1\u2060")
    .replace(/([\])])/g, "\u2060$1");
}

function buildNormalizedMap(text) {
  const lower = text.toLowerCase();
  let normalized = "";
  const positions = [];
  let lastWasSep = false;
  let lastNonSepEnd = 0;
  for (let i = 0; i < lower.length; i += 1) {
    const c = lower.charCodeAt(i);
    const isAlnum = (c >= 0x61 && c <= 0x7a) || (c >= 0x30 && c <= 0x39);
    if (isAlnum) {
      normalized += lower[i];
      positions.push(i);
      lastWasSep = false;
      lastNonSepEnd = i + 1;
    } else if (!lastWasSep && normalized.length > 0) {
      normalized += " ";
      positions.push(i);
      lastWasSep = true;
    }
  }
  while (normalized.endsWith(" ")) {
    normalized = normalized.slice(0, -1);
    positions.pop();
  }
  positions.push(lastNonSepEnd);
  return { normalized, positions };
}

function emitText(out, text, highlightText = "") {
  const normalized = text.replace(/\s+/g, " ");
  keepEdgePunctuationWithPreviousWord(out, normalized);
  if (!highlightText) {
    out.push(escapeHtml(protectInlinePunctuation(normalized)));
    return;
  }

  const { normalized: hay, positions } = buildNormalizedMap(normalized);
  const needle = highlightText.toLowerCase();
  let searchPos = 0;
  let lastEmitted = 0;
  while (needle.length > 0) {
    const hit = hay.indexOf(needle, searchPos);
    if (hit < 0) break;
    const start = positions[hit];
    const end = positions[hit + needle.length];
    if (start > lastEmitted) {
      out.push(escapeHtml(protectInlinePunctuation(normalized.slice(lastEmitted, start))));
    }
    out.push(`<mark class="query-hit">${escapeHtml(protectInlinePunctuation(normalized.slice(start, end)))}</mark>`);
    lastEmitted = end;
    searchPos = hit + needle.length;
  }
  if (lastEmitted < normalized.length) {
    out.push(escapeHtml(protectInlinePunctuation(normalized.slice(lastEmitted))));
  }
}

const VULGAR_FRACTIONS = {
  "1/2": "½", "1/3": "⅓", "2/3": "⅔", "1/4": "¼", "3/4": "¾",
  "1/5": "⅕", "2/5": "⅖", "3/5": "⅗", "4/5": "⅘",
  "1/6": "⅙", "5/6": "⅚",
  "1/7": "⅐",
  "1/8": "⅛", "3/8": "⅜", "5/8": "⅝", "7/8": "⅞",
  "1/9": "⅑",
  "1/10": "⅒",
};

function renderSourceHtml(source, targetLogical = null, options = {}) {
  source = source.replace(
    /<fr>\s*<nu>\s*(\d+)\s*<\/nu>\s*<dn>\s*(\d+)\s*<\/dn>\s*<\/fr>/g,
    (_, num, den) => VULGAR_FRACTIONS[`${num}/${den}`] ?? `${num}⁄${den}`,
  );
  const out = [];
  const stack = [];
  let lastWasBreak = false;
  const highlightableTags = new Set(["hw", "bl"]);
  const highlightText = normalizeSearch(options.highlightText ?? "");
  const isGreekContext = () => stack.some((item) => stackName(item) === "gk");
  const emit = (text) => {
    if (lastWasBreak) {
      text = text.replace(/^\s+/, "");
      if (!text) return;
    }
    if (isGreekContext()) text = decodeGreekText(text);
    const canHighlight = stack.some((item) => highlightableTags.has(stackName(item)));
    emitText(out, text, canHighlight ? highlightText : "");
  };
  const stackName = (item) => (typeof item === "string" ? item : item.name);
  const stackClose = (item) => (typeof item === "string" ? "</span>" : item.close);

  const lineBreak = () => {
    if (!lastWasBreak) out.push("<br>");
    lastWasBreak = true;
  };

  const nextTagAfter = (index) => {
    let cursor = index;
    for (;;) {
      while (/\s/.test(source[cursor] ?? "")) cursor += 1;
      if (source.charCodeAt(cursor) !== 0xe000) break;
      const markerEnd = source.indexOf("\ue001", cursor + 1);
      if (markerEnd < 0) break;
      cursor = markerEnd + 1;
    }
    if (source[cursor] !== "<") return { name: "", closing: false };
    const tagEnd = source.indexOf(">", cursor);
    if (tagEnd < 0) return { name: "", closing: false };
    return tagName(source.slice(cursor, tagEnd + 1));
  };

  const closeTo = (name) => {
    for (let i = stack.length - 1; i >= 0; i -= 1) {
      const item = stack.pop();
      out.push(stackClose(item));
      if (stackName(item) === name) break;
    }
  };

  for (let pos = 0; pos < source.length;) {
    if (source.charCodeAt(pos) === 0xe000) {
      const end = source.indexOf("\ue001", pos + 1);
      if (end >= 0) {
        const logical = source.slice(pos + 1, end);
        const targetClass = logical === targetLogical ? " target-record" : "";
        if (targetClass) {
          out.push(`<span id="rec-${logical}" class="record-anchor${targetClass}"></span>`);
        }
        pos = end + 1;
        continue;
      }
    }
    if (source.startsWith("<ph>", pos)) {
      const end = source.indexOf("</ph>", pos);
      if (end >= 0) {
        out.push(`<span class="tag-ph">${escapeHtml(decodePhoneticText(source.slice(pos + 4, end)))}</span>`);
        pos = end + "</ph>".length;
        lastWasBreak = false;
        continue;
      }
    }
    const ch = source[pos];
    if (ch === "<") {
      const end = source.indexOf(">", pos);
      if (end < 0) break;
      const rawTag = source.slice(pos, end + 1);
      const { name, closing } = tagName(rawTag);
      if (name === "pr") {
        emit(closing ? ")" : "(");
      } else if (name === "etym") {
        emit(closing ? "] " : "[");
        if (closing) lineBreak();
      } else if (name === "vfl" && closing) {
        closeTo(name);
        lineBreak();
      } else if (name === "n") {
        if (!closing) lineBreak();
        else if (nextTagAfter(end + 1).name !== "etym") lineBreak();
      } else if (name === "qp" && !closing) {
        lineBreak();
      } else if (name === "q" && !closing) {
        lineBreak();
        out.push('<span class="tag-q">');
        stack.push(name);
      } else if (name === "sub" && !closing) {
        lineBreak();
        out.push('<span class="tag-sub">');
        stack.push(name);
      } else if (/^s\d+$/.test(name) && !closing) {
        lineBreak();
        const num = rawTag.match(/\bnum=["']?([^"'\s>]+)/i)?.[1];
        if (num) out.push(`<span class="sense-number">${escapeHtml(num)}.</span> `);
      } else if (name === "table") {
        if (closing) {
          closeTo("table");
        } else {
          lineBreak();
          out.push('<table class="oed-table"><tbody>');
          stack.push({ name: "table", close: "</tbody></table>" });
        }
      } else if (name === "l") {
        if (closing) out.push("</td></tr>");
        else out.push("<tr><td>");
      } else if (name === "par") {
        lineBreak();
      } else if (STYLE_TAGS.has(name)) {
        if (!WRAPPED_STYLE_TAGS.has(name)) {
          // Known but visually redundant wrappers are ignored to keep inline layout clean.
        } else if ((name === "x" || name === "xid") && !closing) {
          out.push(`<a class="tag-${name} ref-link" href="#">`);
          stack.push({ name, close: "</a>" });
        } else if (closing) {
          closeTo(name);
        } else {
          out.push(`<span class="tag-${name}">`);
          stack.push(name);
        }
      }
      pos = end + 1;
      continue;
    }
    if (ch === "&") {
      const match = source.slice(pos).match(/^&[A-Za-z0-9]+\.?/);
      if (match) {
        if (match[0] === "&tab." && stack.some((item) => stackName(item) === "table")) {
          out.push("</td><td>");
          pos += match[0].length;
          lastWasBreak = false;
          continue;
        }
        if (isGreekContext()) {
          const greek = greekEntityPreview(match[0]);
          out.push(escapeHtml(greek ?? match[0]));
        } else {
          emit(entityPreview(match[0]));
        }
        pos += match[0].length;
        lastWasBreak = false;
        continue;
      }
    }
    let nextText = pos + 1;
    while (
      nextText < source.length &&
      source[nextText] !== "<" &&
      source[nextText] !== "&" &&
      source.charCodeAt(nextText) !== 0xe000
    ) {
      nextText += 1;
    }
    emit(source.slice(pos, nextText));
    lastWasBreak = false;
    pos = nextText;
  }
  while (stack.length) {
    out.push(stackClose(stack.pop()));
  }
  return out.join("").replace(/(?:\s*<br>\s*){2,}/g, "<br>");
}

export function renderArticleHtml(data) {
  return renderSourceHtml(bytesToText(data));
}

export function renderArticleRecordsHtml(records, targetLogical = null, options = {}) {
  const source = records.map((record) => {
    const text = bytesToText(record.data);
    if (record.logicalOffset === targetLogical) {
      return `\ue000${record.logicalOffset.toString(16)}\ue001${text}`;
    }
    return text;
  }).join("");
  const target = targetLogical === null ? null : targetLogical.toString(16);
  return renderSourceHtml(source, target, options);
}

export function normalizeSearch(text) {
  return text
    .replace(/&[A-Za-z0-9]+\.?/g, "")
    .replaceAll("\u00e6", "ae")
    .replaceAll("\u00c6", "ae")
    .replaceAll("\u0153", "oe")
    .replaceAll("\u0152", "oe")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/['\u2019]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .replace(/\s+/g, " ");
}

export function bodyGeometrySummary(control) {
  return `${control.blockCount.toLocaleString()} blocks, ` +
    `${control.logicalTotal.toLocaleString()} logical records`;
}
