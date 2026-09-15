import { allowedRelations, RESOURCE_SPECS } from "./spec";
import type { AwsRelationship, AwsResource, CostEstimate, Relation } from "./types";
import { formatCents } from "./money";

interface NodeProps {
  resource: AwsResource;
  estimate: CostEstimate | undefined;
  currency: string;
  onChange: (patch: Partial<AwsResource>) => void;
  onField: (group: "configuration" | "usage", key: string, value: unknown) => void;
  onDelete: () => void;
}

export function NodeInspector({
  resource, estimate, currency, onChange, onField, onDelete,
}: NodeProps) {
  const spec = RESOURCE_SPECS[resource.resource_type];
  const money = (cents: bigint) =>
    currency === "USD" ? `$${formatCents(cents)}` : `${formatCents(cents)} ${currency}`;

  return (
    <div className="inspector">
      <label className="field">
        <span>Name</span>
        <input value={resource.name} onChange={(e) => onChange({ name: e.target.value })} />
      </label>
      <p className="muted">{spec.label} · {resource.id}</p>

      {spec.fields.map((field) => {
        const source = field.group === "configuration" ? resource.configuration : resource.usage ?? {};
        const value = source[field.key];
        return (
          <label className="field" key={`${field.group}.${field.key}`}>
            <span>{field.label}</span>
            {field.kind === "select" ? (
              <select
                value={String(value ?? "")}
                onChange={(e) => onField(field.group, field.key, e.target.value)}
              >
                {(field.options ?? []).map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            ) : (
              <input
                type={field.kind}
                value={value === undefined || value === null ? "" : String(value)}
                min={field.min}
                max={field.max}
                step={field.step}
                onChange={(e) =>
                  onField(
                    field.group,
                    field.key,
                    field.kind === "number" ? Number(e.target.value) : e.target.value,
                  )
                }
              />
            )}
          </label>
        );
      })}

      {estimate && (
        <section>
          <h3>Preview cost <span className={`tag ${estimate.status}`}>{estimate.status}</span></h3>
          <p className="big">{money(estimate.cents)} / month</p>
          <ul>
            {estimate.breakdown.map((item) => (
              <li key={item.name}>{item.name}: {money(item.cents)}</li>
            ))}
            {estimate.missing.map((item) => (
              <li key={item} className="missing">{item}</li>
            ))}
          </ul>
        </section>
      )}

      <button className="danger" type="button" onClick={onDelete}>Delete resource</button>
    </div>
  );
}

interface EdgeProps {
  relationship: AwsRelationship;
  sourceType: AwsResource["resource_type"];
  targetType: AwsResource["resource_type"];
  sourceName: string;
  targetName: string;
  onRelation: (relation: Relation) => void;
  onDelete: () => void;
}

export function EdgeInspector({
  relationship, sourceType, targetType, sourceName, targetName, onRelation, onDelete,
}: EdgeProps) {
  const options = allowedRelations(sourceType, targetType);
  return (
    <div className="inspector">
      <p className="muted">{sourceName} → {targetName}</p>
      <label className="field">
        <span>Relation</span>
        <select
          value={relationship.relation}
          onChange={(e) => onRelation(e.target.value as Relation)}
        >
          {options.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </label>
      <button className="danger" type="button" onClick={onDelete}>Delete relationship</button>
    </div>
  );
}
