export type PublicRoute = {
  path: string;
  label: string;
  description: string;
  changeFrequency: "weekly" | "monthly";
  priority: number;
};

export const PUBLIC_CONTENT_ROUTES = [
  {
    path: "/",
    label: "Home",
    description: "Product overview for SRS ambiguity analysis.",
    changeFrequency: "weekly",
    priority: 1,
  },
  {
    path: "/features",
    label: "Features",
    description:
      "Capabilities for deterministic SRS analysis, reports, history, dashboard, and optional AI assistance.",
    changeFrequency: "monthly",
    priority: 0.9,
  },
  {
    path: "/how-it-works",
    label: "How it works",
    description:
      "Workflow from SRS input or upload through segmentation, deterministic detection, scoring, and reports.",
    changeFrequency: "monthly",
    priority: 0.9,
  },
  {
    path: "/resources",
    label: "Resources",
    description: "Educational guides about SRS ambiguity and writing clearer requirements.",
    changeFrequency: "monthly",
    priority: 0.7,
  },
  {
    path: "/resources/what-is-srs-ambiguity",
    label: "What is SRS ambiguity?",
    description:
      "Learn what ambiguity means in Software Requirements Specifications and why it creates delivery risk.",
    changeFrequency: "monthly",
    priority: 0.6,
  },
  {
    path: "/resources/write-clearer-requirements",
    label: "Write clearer requirements",
    description:
      "Practical patterns for making requirements more measurable, specific, clear, and complete.",
    changeFrequency: "monthly",
    priority: 0.6,
  },
] as const satisfies readonly PublicRoute[];

export type AmbiguityCategory = {
  detectorId: string;
  name: string;
  explanation: string;
  example: string;
  risk: string;
  clarification: string;
};

export const DETECTED_AMBIGUITY_CATEGORIES = [
  {
    detectorId: "vague-quantifier",
    name: "Vague quantifiers",
    explanation:
      "Words such as “several”, “many”, or “a number of” name an amount without defining the amount.",
    example: "The system shall support several payment methods.",
    risk: "Teams may implement different numbers of payment methods and still believe they satisfied the requirement.",
    clarification:
      "Specify the exact count or accepted range, such as “at least five payment methods”.",
  },
  {
    detectorId: "subjective-term",
    name: "Subjective terms",
    explanation:
      "Quality words such as “fast”, “easy”, “robust”, or “user-friendly” depend on the reader’s expectations.",
    example: "The dashboard shall load quickly.",
    risk: "Design, engineering, and QA can disagree about whether the finished behavior is acceptable.",
    clarification:
      "Replace the adjective with an observable threshold, such as a response-time or usability criterion.",
  },
  {
    detectorId: "missing-measurable-criteria",
    name: "Missing measurable criteria",
    explanation:
      "A requirement asks for acceptable performance or quality without giving a testable measurement.",
    example: "The application shall provide acceptable search performance.",
    risk: "Acceptance testing becomes subjective because no pass/fail condition is available.",
    clarification:
      "Add a measurable target and operating condition, such as “95% of searches return within 800 ms for 10,000 indexed items”.",
  },
  {
    detectorId: "ambiguous-operator",
    name: "Ambiguous operators",
    explanation:
      "Phrases such as “and/or”, “etc.”, and “and so on” leave the actual set of required behavior open-ended.",
    example: "The report shall export CSV, PDF, etc.",
    risk: "The team may not know which formats are mandatory and which are merely examples.",
    clarification:
      "List the complete required set or split mandatory and optional formats into separate requirements.",
  },
  {
    detectorId: "undefined-terminology",
    name: "Undefined terminology",
    explanation:
      "Domain phrases such as “standard process” or “business rules” can be unclear when no definition is attached.",
    example: "The system shall follow the standard approval workflow.",
    risk: "Different stakeholders may refer to different standards or workflows.",
    clarification:
      "Reference the named policy, glossary entry, workflow document, or explicit rule set.",
  },
  {
    detectorId: "passive-actor",
    name: "Passive voice / unclear actor",
    explanation:
      "Passive constructions can describe an action without naming who or what performs it.",
    example: "A notification shall be sent when payment fails.",
    risk: "Responsibility can be unclear: backend service, email provider, admin user, or another system.",
    clarification:
      "Name the actor, such as “The billing service shall send an email notification when payment fails”.",
  },
  {
    detectorId: "pronoun-reference",
    name: "Pronoun references",
    explanation:
      "Pronouns such as “it”, “they”, or “this” can point to more than one preceding noun or process.",
    example: "When the gateway receives the payment request from the client, it shall validate it.",
    risk: "Readers may not know whether “it” refers to the gateway, client, request, or another component.",
    clarification: "Repeat the noun or split the sentence so each actor and object is explicit.",
  },
  {
    detectorId: "absolute-language",
    name: "Absolute language",
    explanation:
      "Words such as “always”, “never”, “all”, or “instant” can create unrealistic or exception-free obligations.",
    example: "The system shall always be available instantly.",
    risk: "The requirement may be impossible to verify or satisfy under maintenance, outage, or degraded-network conditions.",
    clarification: "Define realistic service levels, exceptions, and measurement windows.",
  },
  {
    detectorId: "optional-language",
    name: "Optional language",
    explanation:
      "Words such as “may”, “might”, “could”, “if possible”, or “when necessary” blur whether behavior is required.",
    example: "The system may notify users when a report is ready.",
    risk: "Developers may treat the behavior as optional while stakeholders expect it as mandatory.",
    clarification:
      "State whether the behavior is required, optional, or conditionally required with clear conditions.",
  },
  {
    detectorId: "missing-constraint",
    name: "Missing constraints",
    explanation:
      "A behavior is requested without boundary conditions such as volume, time, role, locale, or failure behavior.",
    example: "The system shall store audit logs.",
    risk: "Retention, access, scale, and compliance expectations may be interpreted differently.",
    clarification:
      "Add constraints such as retention period, access roles, expected volume, storage location, or deletion behavior.",
  },
  {
    detectorId: "incomplete-requirement",
    name: "Incomplete requirements",
    explanation:
      "Fragments, placeholders, or dangling modal verbs do not describe a complete testable behavior.",
    example: "The system shall…",
    risk: "Implementation cannot proceed reliably because the expected behavior is missing.",
    clarification:
      "Rewrite as a complete requirement with actor, condition, behavior, and acceptance criteria.",
  },
] as const satisfies readonly AmbiguityCategory[];

export const HEALTH_DIMENSIONS = [
  {
    name: "Measurability",
    copy: "Whether the requirement can be evaluated with an objective pass/fail signal.",
  },
  {
    name: "Specificity",
    copy: "Whether quantities, terms, and scope are precise enough for implementation and review.",
  },
  {
    name: "Clarity",
    copy: "Whether actors, references, and operators are understandable to different readers.",
  },
  {
    name: "Completeness",
    copy: "Whether enough conditions, constraints, and behavior are present to act on the requirement.",
  },
] as const;

export const RESOURCE_CARDS = [
  {
    title: "What is SRS ambiguity?",
    href: "/resources/what-is-srs-ambiguity",
    summary:
      "A practical explanation of ambiguity in Software Requirements Specifications, with examples and review guidance.",
  },
  {
    title: "How to write clearer requirements",
    href: "/resources/write-clearer-requirements",
    summary:
      "A concise checklist for making requirements measurable, specific, clear, and complete before implementation.",
  },
] as const;
