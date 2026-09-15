import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeProps,
} from "@xyflow/react";
import { useCallback, useMemo, useState } from "react";

import { EdgeInspector, NodeInspector } from "./Inspector";
import { createResource, download, newId, normalize, serialize } from "./io";
import { formatCents } from "./money";
import { estimateAll } from "./pricing";
import { allowedRelations, RESOURCE_ORDER, RESOURCE_SPECS } from "./spec";
import type { Architecture, AwsResource, PricingCatalog, Relation, ResourceType } from "./types";

type Selection = { kind: "node" | "edge"; id: string } | null;

interface ResourceNodeData extends Record<string, unknown> {
  label: string;
  type: ResourceType;
  cost: string;
  status: string;
}

function ResourceNode({ data, selected }: NodeProps<Node<ResourceNodeData>>) {
  return (
    <div className={`rf-node${selected ? " selected" : ""} status-${data.status}`}>
      <Handle type="target" position={Position.Top} />
      <strong>{data.label}</strong>
      <span className="muted">{data.type} · {data.cost}</span>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = { resource: ResourceNode };

export function App({
  initial,
  catalog,
}: {
  initial: Architecture;
  catalog: PricingCatalog;
}) {
  const [architecture, setArchitecture] = useState<Architecture>(initial);
  const [selection, setSelection] = useState<Selection>(null);
  const [notice, setNotice] = useState<string>("");

  const currency = architecture.pricing_context.currency;
  const money = (cents: bigint) =>
    currency === "USD" ? `$${formatCents(cents)}` : `${formatCents(cents)} ${currency}`;

  const { total, byId } = useMemo(
    () => estimateAll(architecture.resources, catalog),
    [architecture.resources, catalog],
  );

  const nodes = useMemo<Node<ResourceNodeData>[]>(
    () =>
      architecture.resources.map((resource, index) => {
        const estimate = byId.get(resource.id);
        return {
          id: resource.id,
          type: "resource",
          position: architecture.layout.positions[resource.id] ?? { x: 40, y: index * 110 },
          selected: selection?.kind === "node" && selection.id === resource.id,
          data: {
            label: resource.name,
            type: resource.resource_type,
            cost: money(estimate?.cents ?? 0n),
            status: estimate?.status ?? "unpriced",
          },
        };
      }),
    [architecture, byId, selection],
  );

  const edges = useMemo<Edge[]>(
    () =>
      architecture.relationships.map((relationship) => ({
        id: relationship.id,
        source: relationship.source,
        target: relationship.target,
        label: relationship.relation,
        selected: selection?.kind === "edge" && selection.id === relationship.id,
      })),
    [architecture.relationships, selection],
  );

  const typeOf = useCallback(
    (id: string) => architecture.resources.find((r) => r.id === id)?.resource_type,
    [architecture.resources],
  );

  const removeResource = useCallback((id: string) => {
    setArchitecture((current) => ({
      ...current,
      resources: current.resources.filter((r) => r.id !== id),
      relationships: current.relationships.filter((r) => r.source !== id && r.target !== id),
    }));
    setSelection(null);
  }, []);

  const removeRelationship = useCallback((id: string) => {
    setArchitecture((current) => ({
      ...current,
      relationships: current.relationships.filter((r) => r.id !== id),
    }));
    setSelection(null);
  }, []);

  const onNodesChange = useCallback(
    (changes: NodeChange<Node<ResourceNodeData>>[]) => {
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          const { id, position } = change;
          setArchitecture((current) => ({
            ...current,
            layout: { positions: { ...current.layout.positions, [id]: position } },
          }));
        } else if (change.type === "remove") {
          removeResource(change.id);
        } else if (change.type === "select" && change.selected) {
          setSelection({ kind: "node", id: change.id });
        }
      }
    },
    [removeResource],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      for (const change of changes) {
        if (change.type === "remove") removeRelationship(change.id);
        else if (change.type === "select" && change.selected) {
          setSelection({ kind: "edge", id: change.id });
        }
      }
    },
    [removeRelationship],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      const source = typeOf(connection.source);
      const target = typeOf(connection.target);
      if (!source || !target) return;
      if (connection.source === connection.target) {
        setNotice("A resource cannot connect to itself.");
        return;
      }
      const options = allowedRelations(source, target);
      if (options.length === 0) {
        setNotice(`No relationship is allowed from ${source} to ${target}.`);
        return;
      }
      const relation = options[0] as Relation;
      const duplicate = architecture.relationships.some(
        (r) => r.source === connection.source && r.target === connection.target && r.relation === relation,
      );
      if (duplicate) {
        setNotice(`${source} already ${relation} that ${target}.`);
        return;
      }
      setNotice("");
      setArchitecture((current) => ({
        ...current,
        relationships: [
          ...current.relationships,
          { id: newId("edge"), source: connection.source, target: connection.target, relation },
        ],
      }));
    },
    [architecture.relationships, typeOf],
  );

  const addResource = useCallback((type: ResourceType, position?: { x: number; y: number }) => {
    setArchitecture((current) => {
      const index = current.resources.filter((r) => r.resource_type === type).length + 1;
      const resource = createResource(type, index);
      return {
        ...current,
        resources: [...current.resources, resource],
        layout: {
          positions: {
            ...current.layout.positions,
            [resource.id]: position ?? { x: 60, y: current.resources.length * 110 + 40 },
          },
        },
      };
    });
  }, []);

  const patchResource = useCallback((id: string, patch: Partial<AwsResource>) => {
    setArchitecture((current) => ({
      ...current,
      resources: current.resources.map((r) => (r.id === id ? { ...r, ...patch } : r)),
    }));
  }, []);

  const patchField = useCallback(
    (id: string, group: "configuration" | "usage", key: string, value: unknown) => {
      setArchitecture((current) => ({
        ...current,
        resources: current.resources.map((r) =>
          r.id === id ? { ...r, [group]: { ...(r[group] ?? {}), [key]: value } } : r,
        ),
      }));
    },
    [],
  );

  const setRelation = useCallback((id: string, relation: Relation) => {
    setArchitecture((current) => ({
      ...current,
      relationships: current.relationships.map((r) => (r.id === id ? { ...r, relation } : r)),
    }));
  }, []);

  const importFile = useCallback(async (file: File) => {
    try {
      setArchitecture(normalize(JSON.parse(await file.text())));
      setSelection(null);
      setNotice("");
    } catch (error) {
      setNotice(`Could not read that file: ${String(error)}`);
    }
  }, []);

  const selectedResource =
    selection?.kind === "node"
      ? architecture.resources.find((r) => r.id === selection.id)
      : undefined;
  const selectedRelationship =
    selection?.kind === "edge"
      ? architecture.relationships.find((r) => r.id === selection.id)
      : undefined;

  return (
    <div className="app">
      <header>
        <input
          className="title"
          value={architecture.metadata.name}
          onChange={(e) =>
            setArchitecture((current) => ({ ...current, metadata: { name: e.target.value } }))
          }
        />
        <span className="muted">
          {architecture.pricing_context.region} · catalog {architecture.pricing_context.catalog_id}
        </span>
        <span className="total">{money(total)} / month</span>
        <label className="button">
          Import
          <input
            type="file"
            accept=".json,application/json"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void importFile(file);
              e.target.value = "";
            }}
          />
        </label>
        <button type="button" onClick={() => download(architecture)}>
          Export .awsgraph.json
        </button>
      </header>

      {notice && <p className="notice" role="status">{notice}</p>}

      <main>
        <aside className="palette">
          <h2>Palette</h2>
          {RESOURCE_ORDER.map((type) => (
            <button
              key={type}
              type="button"
              draggable
              onDragStart={(e) => e.dataTransfer.setData("text/awsgraph", type)}
              onClick={() => addResource(type)}
            >
              {RESOURCE_SPECS[type].label}
            </button>
          ))}
          <p className="muted">Drag onto the canvas, or click to add.</p>
        </aside>

        <div
          className="canvas"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            const type = e.dataTransfer.getData("text/awsgraph") as ResourceType;
            if (!type) return;
            const bounds = e.currentTarget.getBoundingClientRect();
            addResource(type, { x: e.clientX - bounds.left - 80, y: e.clientY - bounds.top - 20 });
          }}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onPaneClick={() => setSelection(null)}
            deleteKeyCode="Delete"
            fitView
          >
            <Background />
            <Controls />
          </ReactFlow>
        </div>

        <aside className="details">
          {selectedResource ? (
            <NodeInspector
              resource={selectedResource}
              estimate={byId.get(selectedResource.id)}
              currency={currency}
              onChange={(patch) => patchResource(selectedResource.id, patch)}
              onField={(group, key, value) => patchField(selectedResource.id, group, key, value)}
              onDelete={() => removeResource(selectedResource.id)}
            />
          ) : selectedRelationship ? (
            <EdgeInspector
              relationship={selectedRelationship}
              sourceType={typeOf(selectedRelationship.source)!}
              targetType={typeOf(selectedRelationship.target)!}
              sourceName={
                architecture.resources.find((r) => r.id === selectedRelationship.source)?.name ?? ""
              }
              targetName={
                architecture.resources.find((r) => r.id === selectedRelationship.target)?.name ?? ""
              }
              onRelation={(relation) => setRelation(selectedRelationship.id, relation)}
              onDelete={() => removeRelationship(selectedRelationship.id)}
            />
          ) : (
            <details className="export">
              <summary>Design JSON</summary>
              <textarea readOnly value={serialize(architecture)} rows={20} />
            </details>
          )}
        </aside>
      </main>
    </div>
  );
}
