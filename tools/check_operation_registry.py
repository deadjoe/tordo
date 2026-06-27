import ast
from pathlib import Path

from tordo.plan_preflight import CLIP_TARGET_OPERATIONS, SCENE_TARGET_OPERATIONS, TRACK_TARGET_OPERATIONS
from tordo.schema import agent_plan_schema

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = REPO_ROOT / "remote-script" / "TordoBridge" / "bridge.py"
DOCTOR_PATH = REPO_ROOT / "tordo" / "doctor.py"


def main():
    schema = agent_plan_schema()
    schema_targets = schema["operation_targets"]
    schema_ops = set(schema_targets)
    bridge_tree = ast.parse(BRIDGE_PATH.read_text())
    doctor_tree = ast.parse(DOCTOR_PATH.read_text())
    capability_ops = set(extract_capability_operations(bridge_tree))
    dispatch_ops = set(extract_dispatch_operations(bridge_tree))

    failures = []
    compare_sets(failures, "schema operations", schema_ops, "bridge capabilities", capability_ops)
    compare_sets(failures, "schema operations", schema_ops, "bridge dispatch", dispatch_ops)
    compare_sets(
        failures,
        "track-target operations",
        operations_targeting(schema_targets, "track"),
        "preflight TRACK_TARGET_OPERATIONS",
        TRACK_TARGET_OPERATIONS,
    )
    compare_sets(
        failures,
        "scene-target operations",
        operations_targeting(schema_targets, "scene"),
        "preflight SCENE_TARGET_OPERATIONS",
        SCENE_TARGET_OPERATIONS,
    )
    compare_sets(
        failures,
        "clip-target operations",
        operations_targeting(schema_targets, "clip"),
        "preflight CLIP_TARGET_OPERATIONS",
        CLIP_TARGET_OPERATIONS,
    )
    check_destructive_guards(
        failures,
        set(schema["destructive_operations"]),
        bridge_tree,
    )
    check_bridge_version_sync(failures, bridge_tree, doctor_tree)

    if failures:
        raise SystemExit("\n".join(failures))
    print("operation registry check passed: %s operations" % len(schema_ops))


def extract_capability_operations(tree):
    capabilities = find_function(tree, "_capabilities")
    for node in ast.walk(capabilities):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if constant_value(key) == "plan_operations":
                return literal_string_list(value, "plan_operations")
    raise ValueError("bridge capabilities plan_operations not found")


def extract_dispatch_operations(tree):
    apply_plan = find_function(tree, "apply_plan")
    operations = []
    for node in ast.walk(apply_plan):
        if not isinstance(node, ast.Compare):
            continue
        if not isinstance(node.left, ast.Name) or node.left.id != "operation_type":
            continue
        if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
            continue
        if len(node.comparators) != 1:
            continue
        value = constant_value(node.comparators[0])
        if isinstance(value, str):
            operations.append(value)
    if not operations:
        raise ValueError("bridge apply_plan operation dispatch not found")
    return operations


def find_function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise ValueError("function not found: %s" % name)


def check_destructive_guards(failures, destructive_operations, tree):
    missing_from_schema = sorted(destructive_operations - set(agent_plan_schema()["operation_targets"]))
    if missing_from_schema:
        failures.append("destructive operations missing from schema operations: %s" % ", ".join(missing_from_schema))
    for operation in sorted(destructive_operations):
        function_name = "apply_%s" % operation
        try:
            function = find_function(tree, function_name)
        except ValueError as exc:
            failures.append(str(exc))
            continue
        if not calls_require_allow_destructive(function, operation):
            failures.append("%s must call require_allow_destructive(operation, %r)" % (function_name, operation))


def calls_require_allow_destructive(function, operation):
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "require_allow_destructive":
            continue
        if len(node.args) < 2:
            continue
        if not isinstance(node.args[0], ast.Name) or node.args[0].id != "operation":
            continue
        if constant_value(node.args[1]) == operation:
            return True
    return False


def check_bridge_version_sync(failures, bridge_tree, doctor_tree):
    bridge_version = find_module_constant(bridge_tree, "BRIDGE_VERSION")
    doctor_expected_version = find_module_constant(doctor_tree, "EXPECTED_BRIDGE_VERSION")
    if bridge_version != doctor_expected_version:
        failures.append(
            "doctor EXPECTED_BRIDGE_VERSION %r does not match bridge BRIDGE_VERSION %r"
            % (doctor_expected_version, bridge_version)
        )


def find_module_constant(tree, name):
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return constant_value(node.value)
    raise ValueError("module constant not found: %s" % name)


def literal_string_list(node, label):
    try:
        value = ast.literal_eval(node)
    except Exception as exc:
        raise ValueError("%s must be a literal list: %s" % (label, exc)) from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("%s must be a list of strings" % label)
    return value


def constant_value(node):
    if isinstance(node, ast.Constant):
        return node.value
    return None


def operations_targeting(schema_targets, target):
    return {operation for operation, targets in schema_targets.items() if target in targets}


def compare_sets(failures, left_label, left, right_label, right):
    missing_from_right = sorted(left - right)
    missing_from_left = sorted(right - left)
    if missing_from_right:
        failures.append("%s missing from %s: %s" % (left_label, right_label, ", ".join(missing_from_right)))
    if missing_from_left:
        failures.append("%s missing from %s: %s" % (right_label, left_label, ", ".join(missing_from_left)))


if __name__ == "__main__":
    main()
