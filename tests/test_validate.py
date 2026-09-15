from awsgraph.load import parse_design
from awsgraph.validate import validate_design


def resource(rid, rtype, **extra):
    node = {"id": rid, "name": rid, "resource_type": rtype}
    if rtype == "ec2":
        node["configuration"] = {"instance_type": "t3.medium"}
        node["usage"] = {"instance_count": 1, "hours_per_month": 730}
    elif rtype == "rds":
        node["configuration"] = {
            "engine": "mysql",
            "instance_class": "db.t3.medium",
            "storage_gib": 100,
        }
        node["usage"] = {"instance_count": 1, "hours_per_month": 730}
    node.update(extra)
    return node


def check(resources, relationships):
    architecture = parse_design(
        {
            "metadata": {"name": "T"},
            "resources": resources,
            "relationships": relationships,
        }
    )
    return validate_design(architecture)


def test_valid_design_has_no_errors():
    errors = check(
        [resource("a", "ec2"), resource("b", "rds")],
        [{"id": "e1", "source": "a", "target": "b", "relation": "connects-to"}],
    )
    assert errors == []


def test_duplicate_resource_id():
    errors = check([resource("a", "ec2"), resource("a", "rds")], [])
    assert errors == ["resources[1].id: duplicate resource id 'a'"]


def test_duplicate_relationship_id():
    errors = check(
        [resource("a", "ec2"), resource("b", "rds"), resource("c", "rds")],
        [
            {"id": "e1", "source": "a", "target": "b", "relation": "connects-to"},
            {"id": "e1", "source": "a", "target": "c", "relation": "connects-to"},
        ],
    )
    assert errors == ["relationships[1].id: duplicate relationship id 'e1'"]


def test_dangling_source_and_target():
    errors = check(
        [resource("a", "ec2")],
        [{"id": "e1", "source": "x", "target": "y", "relation": "connects-to"}],
    )
    assert errors == [
        "relationships[0].source: unknown resource id 'x'",
        "relationships[0].target: unknown resource id 'y'",
    ]


def test_self_loop_rejected():
    errors = check(
        [resource("a", "ec2")],
        [{"id": "e1", "source": "a", "target": "a", "relation": "connects-to"}],
    )
    assert errors == ["relationships[0]: self-loop on 'a' is not allowed"]


def test_relation_not_allowed_for_pair():
    errors = check(
        [resource("a", "ec2"), resource("b", "rds")],
        [{"id": "e1", "source": "a", "target": "b", "relation": "contains"}],
    )
    assert errors == [
        "relationships[0].relation: 'contains' is not allowed from ec2 to rds "
        "(allowed: connects-to)"
    ]


def test_pair_with_no_allowed_relation():
    errors = check(
        [resource("v", "vpc"), resource("a", "ec2")],
        [{"id": "e1", "source": "v", "target": "a", "relation": "contains"}],
    )
    assert errors == ["relationships[0].relation: no relationship is allowed from vpc to ec2"]


def test_duplicate_relationship_triple():
    errors = check(
        [resource("a", "ec2"), resource("b", "rds")],
        [
            {"id": "e1", "source": "a", "target": "b", "relation": "connects-to"},
            {"id": "e2", "source": "a", "target": "b", "relation": "connects-to"},
        ],
    )
    assert errors == ["relationships[1]: duplicate 'connects-to' relationship from 'a' to 'b'"]


def test_all_errors_reported_not_just_the_first():
    errors = check(
        [resource("a", "ec2"), resource("a", "ec2"), resource("b", "rds")],
        [
            {"id": "e1", "source": "a", "target": "b", "relation": "contains"},
            {"id": "e2", "source": "zz", "target": "b", "relation": "connects-to"},
        ],
    )
    assert len(errors) == 3


def test_subnet_contains_alb():
    errors = check(
        [
            resource("s", "subnet"),
            resource(
                "lb",
                "alb",
                usage={
                    "load_balancer_count": 1,
                    "hours_per_month": 730,
                    "lcu_hours_per_month": 100,
                },
            ),
        ],
        [{"id": "e1", "source": "s", "target": "lb", "relation": "contains"}],
    )
    assert errors == []


def test_subnet_may_both_contain_and_route_to_a_nat_gateway():
    nat = resource(
        "n",
        "nat-gateway",
        usage={
            "gateway_count": 1,
            "hours_per_month": 730,
            "processed_gb_per_month": 50,
        },
    )
    errors = check(
        [resource("public", "subnet"), resource("private", "subnet"), nat],
        [
            {"id": "e1", "source": "public", "target": "n", "relation": "contains"},
            {"id": "e2", "source": "private", "target": "n", "relation": "routes-to"},
        ],
    )
    assert errors == []


def test_disallowed_relation_lists_every_allowed_one():
    nat = resource(
        "n",
        "nat-gateway",
        usage={
            "gateway_count": 1,
            "hours_per_month": 730,
            "processed_gb_per_month": 50,
        },
    )
    errors = check(
        [resource("s", "subnet"), nat],
        [{"id": "e1", "source": "s", "target": "n", "relation": "connects-to"}],
    )
    assert errors == [
        "relationships[0].relation: 'connects-to' is not allowed from subnet to "
        "nat-gateway (allowed: contains, routes-to)"
    ]
