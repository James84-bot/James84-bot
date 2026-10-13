"""Role-based permissions, enforced on the server for every API action.

Roles are fixed (owner, admin, manager, clerk, auditor) because small
businesses need predictable access rather than a permissions editor. The
mapping lives here in one place so it can be reviewed against the table in
docs/ARCHITECTURE.md.
"""

from enum import StrEnum

from rest_framework.permissions import BasePermission


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    CLERK = "clerk"
    AUDITOR = "auditor"


ROLE_LABELS = {
    Role.OWNER: "Owner",
    Role.ADMIN: "Administrator",
    Role.MANAGER: "Manager",
    Role.CLERK: "Inventory clerk",
    Role.AUDITOR: "Auditor (read-only)",
}


class Perm(StrEnum):
    VIEW = "view"  # read operational records (products, stock, documents)
    MANAGE_ORG = "manage_org"
    MANAGE_USERS = "manage_users"
    MANAGE_MASTER_DATA = "manage_master_data"  # products, suppliers, customers
    VIEW_COSTS = "view_costs"
    RECORD_STOCK = "record_stock"  # receipts, issues, transfers
    ADJUST_STOCK = "adjust_stock"
    CREATE_REQUISITION = "create_requisition"
    APPROVE_REQUISITION = "approve_requisition"
    MANAGE_PURCHASE_ORDERS = "manage_purchase_orders"
    APPROVE_PURCHASE_ORDERS = "approve_purchase_orders"
    RECEIVE_GOODS = "receive_goods"
    MANAGE_SALES = "manage_sales"  # invoices, receipts, credit notes
    VIEW_REPORTS = "view_reports"
    EXPORT = "export"
    VIEW_AUDIT = "view_audit"


_ALL = set(Perm)

ROLE_PERMISSIONS: dict[Role, frozenset[Perm]] = {
    Role.OWNER: frozenset(_ALL),
    Role.ADMIN: frozenset(_ALL - {Perm.MANAGE_ORG}),
    Role.MANAGER: frozenset(
        {
            Perm.VIEW,
            Perm.MANAGE_MASTER_DATA,
            Perm.VIEW_COSTS,
            Perm.RECORD_STOCK,
            Perm.ADJUST_STOCK,
            Perm.CREATE_REQUISITION,
            Perm.APPROVE_REQUISITION,
            Perm.MANAGE_PURCHASE_ORDERS,
            Perm.APPROVE_PURCHASE_ORDERS,
            Perm.RECEIVE_GOODS,
            Perm.MANAGE_SALES,
            Perm.VIEW_REPORTS,
        }
    ),
    Role.CLERK: frozenset({Perm.VIEW, Perm.RECORD_STOCK, Perm.CREATE_REQUISITION, Perm.RECEIVE_GOODS}),
    Role.AUDITOR: frozenset({Perm.VIEW, Perm.VIEW_COSTS, Perm.VIEW_REPORTS, Perm.EXPORT, Perm.VIEW_AUDIT}),
}


def role_has(role: str, perm: Perm) -> bool:
    return perm in ROLE_PERMISSIONS.get(Role(role), frozenset())


class HasOrgPermission(BasePermission):
    """Checks `view.required_permissions[action]` against the member's role.

    Views declare a mapping such as {"list": Perm.VIEW, "create": Perm.MANAGE_MASTER_DATA}.
    An action missing from the mapping is denied, so new endpoints are closed
    by default.
    """

    message = "Your role does not allow this action."

    def has_permission(self, request, view) -> bool:
        membership = getattr(request, "membership", None)
        if membership is None:
            return False
        required = getattr(view, "required_permissions", {})
        action = getattr(view, "action", None) or request.method.lower()
        perm = required.get(action)
        if perm is None:
            return False
        return role_has(membership.role, perm)
