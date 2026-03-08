#!/usr/bin/env python3
"""Pizza MCP demo API server.

This server provides a direct HTTP endpoint so agents can execute the same
pizza ordering tools without using browser UI automation.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

STATE_PATH = Path("/tmp/pizza_mcp_orders.json")
HOST = "0.0.0.0"
PORT = 8081

TAX_RATE = 0.0825
DELIVERY_FEE = 4.5

MENU_ITEMS = {
    "margherita": {
        "id": "margherita",
        "name": "Margherita Pizza",
        "category": "pizza",
        "description": "Tomato sauce, mozzarella, basil",
        "priceBySize": {"small": 11.0, "medium": 14.0, "large": 18.0},
    },
    "pepperoni": {
        "id": "pepperoni",
        "name": "Pepperoni Pizza",
        "category": "pizza",
        "description": "Pepperoni, mozzarella, tomato sauce",
        "priceBySize": {"small": 12.0, "medium": 15.0, "large": 19.0},
    },
    "truffle-mushroom": {
        "id": "truffle-mushroom",
        "name": "Truffle Mushroom Pizza",
        "category": "pizza",
        "description": "Wild mushrooms, truffle cream, mozzarella",
        "priceBySize": {"small": 14.0, "medium": 18.0, "large": 22.0},
    },
    "hawaiian": {
        "id": "hawaiian",
        "name": "Hawaiian Pizza",
        "category": "pizza",
        "description": "Ham, pineapple, mozzarella, tomato sauce",
        "priceBySize": {"small": 12.0, "medium": 16.0, "large": 20.0},
    },
    "caesar-salad": {
        "id": "caesar-salad",
        "name": "Caesar Salad",
        "category": "salad",
        "description": "Romaine, croutons, parmesan",
        "price": 8.0,
    },
    "garlic-knots": {
        "id": "garlic-knots",
        "name": "Garlic Knots",
        "category": "side",
        "description": "Six knots with garlic butter",
        "price": 7.0,
    },
    "cola": {
        "id": "cola",
        "name": "Cola",
        "category": "drink",
        "description": "12oz can",
        "price": 3.0,
    },
    "sparkling-water": {
        "id": "sparkling-water",
        "name": "Sparkling Water",
        "category": "drink",
        "description": "Lemon infused",
        "price": 3.0,
    },
}

ITEM_ALIASES = {
    "cheese_pizza": "margherita",
    "cheese-pizza": "margherita",
    "pepperoni_pizza": "pepperoni",
    "pepperoni-pizza": "pepperoni",
}

EXTRAS = {
    "extra-cheese": {
        "id": "extra-cheese",
        "name": "Extra Cheese",
        "price": 1.8,
        "appliesTo": ["pizza"],
    },
    "basil": {
        "id": "basil",
        "name": "Fresh Basil",
        "price": 0.9,
        "appliesTo": ["pizza"],
    },
    "olives": {
        "id": "olives",
        "name": "Black Olives",
        "price": 1.2,
        "appliesTo": ["pizza", "salad"],
    },
    "jalapeno": {
        "id": "jalapeno",
        "name": "Jalapeno",
        "price": 1.1,
        "appliesTo": ["pizza"],
    },
    "gluten-free-crust": {
        "id": "gluten-free-crust",
        "name": "Gluten-Free Crust",
        "price": 2.5,
        "appliesTo": ["pizza"],
    },
}


class ToolError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class OrderStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._state: Dict[str, Any] = {
            "nextOrderSeq": 1001,
            "orders": {},
            "lastOrderId": "",
        }
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            parsed = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                if isinstance(parsed.get("nextOrderSeq"), int):
                    self._state["nextOrderSeq"] = parsed["nextOrderSeq"]
                if isinstance(parsed.get("orders"), dict):
                    self._state["orders"] = parsed["orders"]
                if isinstance(parsed.get("lastOrderId"), str):
                    self._state["lastOrderId"] = parsed["lastOrderId"]
        except Exception:
            # Keep defaults for demo resilience.
            pass

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._state, ensure_ascii=True), encoding="utf-8")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _to_money(value: float) -> float:
        return round(float(value) + 1e-9, 2)

    @staticmethod
    def _normalize_order_type(value: Any) -> str:
        return "delivery" if str(value).lower() == "delivery" else "pickup"

    @staticmethod
    def _normalize_item_id(raw_item_id: Any) -> str:
        item_id = str(raw_item_id or "").strip().lower()
        if item_id in ITEM_ALIASES:
            return ITEM_ALIASES[item_id]
        return item_id

    @staticmethod
    def _normalize_extras(raw_extras: Any) -> List[str]:
        if raw_extras is None:
            return []
        if isinstance(raw_extras, list):
            values = [str(item).strip().lower() for item in raw_extras]
        else:
            values = [part.strip().lower() for part in str(raw_extras).split(",")]

        deduped: List[str] = []
        seen = set()
        for value in values:
            if value and value not in seen:
                deduped.append(value)
                seen.add(value)
        return deduped

    @staticmethod
    def _parse_quantity(raw_quantity: Any) -> int:
        value = 1 if raw_quantity is None else raw_quantity
        try:
            qty = int(value)
        except Exception as exc:
            raise ToolError("quantity must be an integer between 1 and 20") from exc
        if qty < 1 or qty > 20:
            raise ToolError("quantity must be an integer between 1 and 20")
        return qty

    @staticmethod
    def _parse_tip(raw_tip: Any) -> float:
        value = 0 if raw_tip is None else raw_tip
        try:
            tip = float(value)
        except Exception as exc:
            raise ToolError("tipPercent must be between 0 and 40") from exc
        if tip < 0 or tip > 40:
            raise ToolError("tipPercent must be between 0 and 40")
        return tip

    def _resolve_order_id(self, args: Dict[str, Any]) -> str:
        order_id = str(args.get("orderId") or "").strip().upper()
        if order_id:
            return order_id
        last_order_id = str(self._state.get("lastOrderId") or "").strip().upper()
        if last_order_id:
            return last_order_id
        raise ToolError("orderId is required. Call create_order first.")

    def _get_order(self, order_id: str) -> Dict[str, Any]:
        order = self._state["orders"].get(order_id)
        if not isinstance(order, dict):
            raise ToolError("Order not found: " + order_id, status_code=404)
        return order

    def _choose_size(self, item: Dict[str, Any], raw_size: Any) -> Optional[str]:
        if "priceBySize" not in item:
            return None
        size = str(raw_size or "medium").strip().lower()
        if size not in item["priceBySize"]:
            raise ToolError("Invalid size. Use small, medium, or large.")
        return size

    def _extras_for_item(self, item: Dict[str, Any], raw_extras: Any) -> List[Dict[str, Any]]:
        extra_ids = self._normalize_extras(raw_extras)
        resolved: List[Dict[str, Any]] = []
        for extra_id in extra_ids:
            extra = EXTRAS.get(extra_id)
            if not extra:
                raise ToolError("Unknown extra: " + extra_id)
            if item["category"] not in extra["appliesTo"]:
                raise ToolError(extra["name"] + " cannot be added to " + item["category"])
            resolved.append(extra)
        return resolved

    def _build_line(self, item: Dict[str, Any], size: Optional[str], quantity: int, extras: List[Dict[str, Any]], line_id: int) -> Dict[str, Any]:
        if "priceBySize" in item:
            base_price = float(item["priceBySize"][size or "medium"])
        else:
            base_price = float(item["price"])

        extras_price = sum(float(extra["price"]) for extra in extras)
        unit_price = self._to_money(base_price + extras_price)
        line_total = self._to_money(unit_price * quantity)

        return {
            "lineId": line_id,
            "itemId": item["id"],
            "name": item["name"],
            "size": size,
            "quantity": quantity,
            "extras": [
                {"id": extra["id"], "name": extra["name"], "price": float(extra["price"])}
                for extra in extras
            ],
            "unitPrice": unit_price,
            "lineTotal": line_total,
        }

    def _summary(self, order: Dict[str, Any]) -> Dict[str, Any]:
        lines = []
        subtotal = 0.0
        item_count = 0
        for line in order.get("lines", []):
            subtotal += float(line.get("lineTotal", 0))
            item_count += int(line.get("quantity", 0))
            lines.append(
                {
                    "lineId": int(line["lineId"]),
                    "itemId": line["itemId"],
                    "name": line["name"],
                    "size": line.get("size"),
                    "quantity": int(line["quantity"]),
                    "extras": [extra["id"] for extra in line.get("extras", [])],
                    "unitPrice": self._to_money(float(line["unitPrice"])),
                    "lineTotal": self._to_money(float(line["lineTotal"])),
                }
            )

        return {
            "exists": True,
            "orderId": order["orderId"],
            "createdAt": order.get("createdAt"),
            "updatedAt": order.get("updatedAt"),
            "status": order.get("status"),
            "customerName": order.get("customerName"),
            "phone": order.get("phone"),
            "orderType": order.get("orderType"),
            "address": order.get("address"),
            "lines": lines,
            "itemCount": item_count,
            "subtotal": self._to_money(subtotal),
        }

    def _tracking_stage(self, order: Dict[str, Any]) -> Dict[str, Any]:
        status = str(order.get("status") or "draft")
        if status == "draft":
            return {"stage": "draft", "label": "Draft", "message": "Order is not placed yet."}

        ts = order.get("updatedAt") or order.get("createdAt")
        elapsed_minutes = 0
        if isinstance(ts, str) and ts:
            try:
                normalized = ts.replace("Z", "+00:00")
                elapsed_seconds = datetime.now(timezone.utc).timestamp() - datetime.fromisoformat(normalized).timestamp()
                elapsed_minutes = max(0, int(elapsed_seconds // 60))
            except Exception:
                elapsed_minutes = 0

        order_type = str(order.get("orderType") or "pickup")
        if order_type == "delivery":
            if elapsed_minutes < 3:
                return {"stage": "confirmed", "label": "Confirmed", "message": "Order confirmed by kitchen.", "etaMinutes": 25}
            if elapsed_minutes < 10:
                return {"stage": "preparing", "label": "Preparing", "message": "Chef is preparing your order.", "etaMinutes": 18}
            if elapsed_minutes < 18:
                return {"stage": "baking", "label": "Baking", "message": "Pizza is in the oven.", "etaMinutes": 10}
            if elapsed_minutes < 28:
                return {"stage": "on-the-way", "label": "Out for Delivery", "message": "Courier is on the way.", "etaMinutes": 4}
            return {"stage": "delivered", "label": "Delivered", "message": "Order was delivered."}

        if elapsed_minutes < 3:
            return {"stage": "confirmed", "label": "Confirmed", "message": "Order confirmed by kitchen.", "etaMinutes": 16}
        if elapsed_minutes < 10:
            return {"stage": "preparing", "label": "Preparing", "message": "Chef is preparing your order.", "etaMinutes": 10}
        if elapsed_minutes < 16:
            return {"stage": "baking", "label": "Baking", "message": "Pizza is in the oven.", "etaMinutes": 4}
        return {"stage": "ready", "label": "Ready for Pickup", "message": "Order is ready for pickup."}

    def get_menu(self, args: Dict[str, Any]) -> Dict[str, Any]:
        category = str(args.get("category") or "").strip().lower()
        items = []
        for item in MENU_ITEMS.values():
            if category and item["category"] != category:
                continue
            items.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "category": item["category"],
                    "description": item["description"],
                    "price": item.get("price"),
                    "priceBySize": item.get("priceBySize"),
                }
            )

        return {
            "currency": "USD",
            "category": category or "all",
            "items": items,
            "extras": list(EXTRAS.values()),
        }

    def create_order(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            order_id = f"PZ-{self._state['nextOrderSeq']}"
            self._state["nextOrderSeq"] += 1

            order = {
                "orderId": order_id,
                "createdAt": self._now_iso(),
                "updatedAt": self._now_iso(),
                "status": "draft",
                "customerName": str(args.get("customerName") or "Guest").strip() or "Guest",
                "phone": str(args.get("phone") or "").strip(),
                "orderType": self._normalize_order_type(args.get("orderType") or "pickup"),
                "address": str(args.get("address") or "").strip(),
                "notes": "",
                "lines": [],
                "nextLineId": 1,
            }
            self._state["orders"][order_id] = order
            self._state["lastOrderId"] = order_id
            self._save()

            return {
                "message": "Order created",
                "orderId": order_id,
                "order": self._summary(order),
            }

    def update_order_details(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            order_id = self._resolve_order_id(args)
            order = self._get_order(order_id)

            if "customerName" in args:
                order["customerName"] = str(args.get("customerName") or "Guest").strip() or "Guest"
            if "phone" in args:
                order["phone"] = str(args.get("phone") or "").strip()
            if "orderType" in args:
                order["orderType"] = self._normalize_order_type(args.get("orderType"))
            if "address" in args:
                order["address"] = str(args.get("address") or "").strip()

            order["updatedAt"] = self._now_iso()
            self._state["lastOrderId"] = order_id
            self._save()

            return {
                "message": "Order details updated",
                "orderId": order_id,
                "order": self._summary(order),
            }

    def add_item(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            order_id = self._resolve_order_id(args)
            order = self._get_order(order_id)

            item_id = self._normalize_item_id(args.get("itemId"))
            if not item_id:
                raise ToolError("itemId is required")
            item = MENU_ITEMS.get(item_id)
            if not item:
                raise ToolError("Unknown itemId: " + item_id)

            size = self._choose_size(item, args.get("size"))
            quantity = self._parse_quantity(args.get("quantity"))
            extras = self._extras_for_item(item, args.get("extras"))

            line_id = int(order.get("nextLineId") or 1)
            order["nextLineId"] = line_id + 1
            line = self._build_line(item, size, quantity, extras, line_id)
            order["lines"].append(line)
            order["updatedAt"] = self._now_iso()
            self._state["lastOrderId"] = order_id
            self._save()

            return {
                "message": "Item added",
                "orderId": order_id,
                "addedLine": line,
                "order": self._summary(order),
            }

    def _find_line_index(self, order: Dict[str, Any], args: Dict[str, Any]) -> int:
        lines = order.get("lines", [])
        if not lines:
            raise ToolError("No order lines available")

        raw_line_id = args.get("lineId")
        if raw_line_id is not None:
            try:
                line_id = int(raw_line_id)
            except Exception as exc:
                raise ToolError("lineId must be an integer") from exc
            for idx, line in enumerate(lines):
                if int(line.get("lineId", 0)) == line_id:
                    return idx
            raise ToolError("Could not find line " + str(line_id))

        item_id = self._normalize_item_id(args.get("itemId"))
        if item_id:
            for idx in range(len(lines) - 1, -1, -1):
                if lines[idx].get("itemId") == item_id:
                    return idx

        if bool(args.get("preferPizza")):
            for idx in range(len(lines) - 1, -1, -1):
                menu_item = MENU_ITEMS.get(lines[idx].get("itemId", ""))
                if menu_item and menu_item.get("category") == "pizza":
                    return idx

        return len(lines) - 1

    def update_item(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            order_id = self._resolve_order_id(args)
            order = self._get_order(order_id)

            line_index = self._find_line_index(order, args)
            current_line = order["lines"][line_index]

            has_updates = any(
                key in args
                for key in ("itemId", "size", "quantity", "extras")
            )
            if not has_updates:
                raise ToolError("Please provide at least one field to update")

            next_item_id = self._normalize_item_id(args.get("itemId", current_line.get("itemId")))
            item = MENU_ITEMS.get(next_item_id)
            if not item:
                raise ToolError("Unknown itemId: " + next_item_id)

            next_size = args.get("size", current_line.get("size"))
            size = self._choose_size(item, next_size)

            next_quantity = args.get("quantity", current_line.get("quantity"))
            quantity = self._parse_quantity(next_quantity)

            if "extras" in args:
                extras_input = args.get("extras")
            else:
                extras_input = [extra.get("id") for extra in current_line.get("extras", [])]
            extras = self._extras_for_item(item, extras_input)

            updated_line = self._build_line(item, size, quantity, extras, int(current_line.get("lineId", 1)))
            order["lines"][line_index] = updated_line
            order["updatedAt"] = self._now_iso()
            self._state["lastOrderId"] = order_id
            self._save()

            return {
                "message": "Item updated",
                "orderId": order_id,
                "updatedLine": updated_line,
                "order": self._summary(order),
            }

    def add_extras(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            order_id = self._resolve_order_id(args)
            order = self._get_order(order_id)
            line_index = self._find_line_index(order, args)
            current_line = order["lines"][line_index]

            incoming = self._normalize_extras(args.get("extras"))
            if not incoming:
                raise ToolError("Please provide extras to add")

            merged = [extra.get("id") for extra in current_line.get("extras", [])] + incoming
            updated = self.update_item(
                {
                    "orderId": order_id,
                    "lineId": current_line.get("lineId"),
                    "extras": merged,
                }
            )
            updated["message"] = "Extras added"
            return updated

    def remove_extras(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            order_id = self._resolve_order_id(args)
            order = self._get_order(order_id)
            line_index = self._find_line_index(order, args)
            current_line = order["lines"][line_index]

            to_remove = set(self._normalize_extras(args.get("extras")))
            if not to_remove:
                raise ToolError("Please provide extras to remove")

            remaining = [
                extra.get("id")
                for extra in current_line.get("extras", [])
                if extra.get("id") not in to_remove
            ]

            updated = self.update_item(
                {
                    "orderId": order_id,
                    "lineId": current_line.get("lineId"),
                    "extras": remaining,
                }
            )
            updated["message"] = "Extras removed"
            return updated

    def remove_item(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            order_id = self._resolve_order_id(args)
            order = self._get_order(order_id)

            raw_line_id = args.get("lineId")
            if raw_line_id is None:
                if not order.get("lines"):
                    raise ToolError("No order lines available")
                line_id = int(order["lines"][-1].get("lineId", 0))
            else:
                try:
                    line_id = int(raw_line_id)
                except Exception as exc:
                    raise ToolError("lineId must be an integer") from exc

            index = -1
            for idx, line in enumerate(order.get("lines", [])):
                if int(line.get("lineId", 0)) == line_id:
                    index = idx
                    break
            if index < 0:
                raise ToolError("Could not find line " + str(line_id))

            removed = order["lines"].pop(index)
            order["updatedAt"] = self._now_iso()
            self._state["lastOrderId"] = order_id
            self._save()

            return {
                "message": "Item removed",
                "orderId": order_id,
                "removedLine": removed,
                "order": self._summary(order),
            }

    def get_order(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            order_id = self._resolve_order_id(args)
            order = self._get_order(order_id)
            self._state["lastOrderId"] = order_id
            return self._summary(order)

    def place_order(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            order_id = self._resolve_order_id(args)
            order = self._get_order(order_id)

            if not order.get("lines"):
                raise ToolError("Cannot place an empty order")

            notes = str(args.get("notes") or "").strip()
            order["status"] = "placed"
            order["notes"] = notes
            order["updatedAt"] = self._now_iso()
            self._state["lastOrderId"] = order_id
            self._save()

            return {
                "message": "Order placed",
                "trackingId": order_id,
                "order": self._summary(order),
            }

    def get_bill(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            order_id = self._resolve_order_id(args)
            order = self._get_order(order_id)

            tip_percent = self._parse_tip(args.get("tipPercent"))
            summary = self._summary(order)
            subtotal = float(summary["subtotal"])
            tax = self._to_money(subtotal * TAX_RATE)
            delivery_fee = DELIVERY_FEE if summary["orderType"] == "delivery" else 0.0
            tip = self._to_money((subtotal * tip_percent) / 100)
            total = self._to_money(subtotal + tax + delivery_fee + tip)

            return {
                "billId": "BILL-" + order_id,
                "currency": "USD",
                "orderId": order_id,
                "status": summary["status"],
                "customerName": summary["customerName"],
                "orderType": summary["orderType"],
                "address": summary["address"],
                "lines": summary["lines"],
                "charges": {
                    "subtotal": self._to_money(subtotal),
                    "taxRatePercent": TAX_RATE * 100,
                    "tax": tax,
                    "deliveryFee": self._to_money(delivery_fee),
                    "tipPercent": tip_percent,
                    "tip": tip,
                },
                "total": total,
            }

    def track_order(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            order_id = self._resolve_order_id(args)
            order = self._get_order(order_id)
            summary = self._summary(order)
            return {
                "orderId": order_id,
                "status": summary["status"],
                "tracking": self._tracking_stage(order),
                "orderType": summary["orderType"],
                "customerName": summary["customerName"],
                "lineCount": len(summary["lines"]),
                "itemCount": summary["itemCount"],
                "updatedAt": summary["updatedAt"],
            }

    def list_orders(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            limit_raw = args.get("limit", 5)
            try:
                limit = int(limit_raw)
            except Exception:
                limit = 5
            limit = max(1, min(20, limit))

            orders = sorted(
                self._state["orders"].values(),
                key=lambda order: str(order.get("updatedAt") or order.get("createdAt") or ""),
                reverse=True,
            )

            entries = []
            for order in orders[:limit]:
                summary = self._summary(order)
                entries.append(
                    {
                        "orderId": summary["orderId"],
                        "status": summary["status"],
                        "tracking": self._tracking_stage(order),
                        "orderType": summary["orderType"],
                        "customerName": summary["customerName"],
                        "itemCount": summary["itemCount"],
                        "updatedAt": summary["updatedAt"],
                    }
                )

            return {"count": len(entries), "orders": entries}


STORE = OrderStore(STATE_PATH)


def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    tool_name = str(name or "").strip()
    args = arguments if isinstance(arguments, dict) else {}

    if tool_name == "get_menu":
        return STORE.get_menu(args)
    if tool_name == "create_order":
        return STORE.create_order(args)
    if tool_name == "update_order_details":
        return STORE.update_order_details(args)
    if tool_name == "add_item":
        return STORE.add_item(args)
    if tool_name == "update_item":
        return STORE.update_item(args)
    if tool_name == "add_extras":
        return STORE.add_extras(args)
    if tool_name == "remove_extras":
        return STORE.remove_extras(args)
    if tool_name == "remove_item":
        return STORE.remove_item(args)
    if tool_name == "get_order":
        return STORE.get_order(args)
    if tool_name == "place_order":
        return STORE.place_order(args)
    if tool_name == "get_bill":
        return STORE.get_bill(args)
    if tool_name == "track_order":
        return STORE.track_order(args)
    if tool_name == "list_orders":
        return STORE.list_orders(args)

    raise ToolError("Unknown tool: " + tool_name)


class Handler(BaseHTTPRequestHandler):
    server_version = "PizzaMCPDemo/1.0"

    def _write_json(self, status_code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _parse_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length") or 0)
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ToolError("Invalid JSON payload") from exc
        if not isinstance(parsed, dict):
            raise ToolError("Request body must be a JSON object")
        return parsed

    def do_OPTIONS(self) -> None:
        self._write_json(HTTPStatus.OK, {"ok": True})

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/health":
            self._write_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "pizza-mcp-api",
                    "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                },
            )
            return

        if path == "/tools":
            self._write_json(
                HTTPStatus.OK,
                {
                    "tools": [
                        "get_menu",
                        "create_order",
                        "update_order_details",
                        "add_item",
                        "update_item",
                        "add_extras",
                        "remove_extras",
                        "remove_item",
                        "get_order",
                        "place_order",
                        "get_bill",
                        "track_order",
                        "list_orders",
                    ]
                },
            )
            return

        self._write_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        try:
            payload = self._parse_body()

            if path == "/tools/call":
                if "jsonrpc" in payload and payload.get("method") == "tools/call":
                    name = payload.get("params", {}).get("name")
                    arguments = payload.get("params", {}).get("arguments", {})
                    result = call_tool(str(name), arguments)
                    response = {
                        "jsonrpc": "2.0",
                        "id": payload.get("id"),
                        "result": {
                            "tool": str(name),
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(result, ensure_ascii=True),
                                }
                            ],
                        },
                    }
                    self._write_json(HTTPStatus.OK, response)
                    return

                name = payload.get("name") or payload.get("tool")
                arguments = payload.get("arguments", {})
                if not name:
                    raise ToolError("name or tool is required")
                result = call_tool(str(name), arguments)
                self._write_json(HTTPStatus.OK, {"ok": True, "tool": str(name), "result": result})
                return

            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
        except ToolError as exc:
            self._write_json(exc.status_code, {"ok": False, "error": str(exc)})
        except Exception:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "Internal server error"})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
