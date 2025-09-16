import os, uuid, sqlite3, datetime as dt
from typing import List, Tuple, Optional, Dict, Any
import streamlit as st
from PIL import Image, ImageDraw
import json

# ============================================================
# App configuration
# ============================================================
APP_TITLE = "Enterprise DMS + Work Management Prototype"
DB_PATH = "dms.sqlite3"
FILES_DIR = "dms_files"
os.makedirs(FILES_DIR, exist_ok=True)

# ============================================================
# Domain configuration
# ============================================================
DOCUMENT_TYPES = ["Policy", "Procedure", "Contract", "Invoice", "PO", "Drawing", "Other"]
DEPARTMENTS = ["Shared Services", "HR", "Finance", "Procurement", "IT", "Operations", "Legal", "Sales", "Marketing", "Engineering"]
SENSITIVITY = ["Public", "Internal", "Confidential", "Restricted"]
RETENTION_POLICIES = {
    "Business record (7y)": 7,
    "Contract life + 6y": 6,
    "Finance (10y)": 10,
    "Until superseded": 0,
    "Custom": -1,
}

# Enhanced approval workflows
APPROVAL_WORKFLOWS = {
    "Simple Approval": {
        "steps": ["Department Manager"],
        "description": "Single manager approval"
    },
    "Standard Review": {
        "steps": ["Department Lead", "Department Manager"],
        "description": "Two-step departmental review"
    },
    "Engineering Review": {
        "steps": ["Engineering Lead", "QA Reviewer", "Engineering Manager"],
        "description": "Technical review workflow"
    },
    "Legal & Finance": {
        "steps": ["Legal Counsel", "Finance Manager"],
        "description": "Legal and finance review"
    },
    "Executive Approval": {
        "steps": ["Department Manager", "Director", "VP"],
        "description": "High-level executive approval"
    }
}

# Workflow step action types
STEP_ACTIONS = {
    "review": "Review Document",
    "approve": "Approve/Reject",
    "sign": "Digital Signature Required",
    "annotate": "Add Comments/Notes",
    "verify": "Verify Information",
    "route": "Route to Next Step"
}

# Workflow triggers and conditions
WORKFLOW_TRIGGERS = {
    "document_type": "Document Type",
    "department": "Department", 
    "sensitivity": "Sensitivity Level",
    "value_threshold": "Dollar Value Threshold",
    "custom_field": "Custom Field Value"
}

# Process templates
PROCESS_TEMPLATES = {
    "Engineering Drawing": ["Engineering Lead", "QA Reviewer", "Engineering Manager"],
    "Policy Update": ["Department Owner", "HR Approver"],
    "Supplier Contract": ["Procurement Lead", "Legal Counsel", "Procurement Manager"],
}

# Demo users
SEED_USERS = [
    ("u-admin", "Admin User", "admin@example.com", "Admin"),
    ("u-vp", "VP", "vp@example.com", "VP"),
    ("u-director", "Director", "director@example.com", "Director"),
    ("u-deptmgr", "Department Manager", "deptmgr@example.com", "Department Manager"),
    ("u-englead", "Engineering Lead", "englead@example.com", "Engineering Lead"),
    ("u-engmgr", "Engineering Manager", "engmgr@example.com", "Engineering Manager"),
    ("u-finmgr", "Finance Manager", "finmgr@example.com", "Finance Manager"),
    ("u-legal", "Legal Counsel", "legal@example.com", "Legal Counsel"),
    ("u-qarev", "QA Reviewer", "qarev@example.com", "QA Reviewer"),
    ("u-deptlead", "Department Lead", "deptlead@example.com", "Department Lead"),
    ("u-approver", "Aisha Approver", "aisha@example.com", "Approver"),
    ("u-contrib", "Omar Contributor", "omar@example.com", "Contributor"),
    ("u-view", "Vera Viewer", "vera@example.com", "Viewer"),
    ("u-deptowner", "Department Owner", "owner@example.com", "Department Owner"),
    ("u-hrappr", "HR Approver", "hrappr@example.com", "HR Approver"),
    ("u-proclead", "Procurement Lead", "proclead@example.com", "Procurement Lead"),
    ("u-procmgr", "Procurement Manager", "procmgr@example.com", "Procurement Manager"),
]

def now_iso() -> str:
    return dt.datetime.utcnow().isoformat(timespec="seconds")

# ============================================================
# Integration stubs
# ============================================================
class SharePointStorageStub:
    enabled = False
    def upload(self, local_path: str, *, site_id: str = "", drive_id: str = "", folder_path: str = ""):
        return {"status": "stubbed", "local_path": local_path, "sharepoint_item_id": None, "url": None}
    def create_metadata_columns(self):
        return {"status": "stubbed"}

class PowerAutomateClientStub:
    def __init__(self, flow_url: Optional[str] = None, api_key: Optional[str] = None):
        self.flow_url = flow_url
        self.api_key = api_key
    def send_event(self, event_name: str, payload: dict):
        return {"status": "stubbed", "event": event_name, "payload": payload}

sp_storage = SharePointStorageStub()
pa_client = PowerAutomateClientStub()

# ============================================================
# DB Setup
# ============================================================
def connect():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = connect()
    cur = conn.cursor()

    # Original tables
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT,
        role TEXT NOT NULL
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        department TEXT,
        doc_type TEXT,
        sensitivity TEXT,
        tags TEXT,
        retention_policy TEXT,
        retention_years INTEGER,
        status TEXT,
        effective_date TEXT,
        expiry_date TEXT,
        created_at TEXT,
        created_by TEXT,
        active INTEGER DEFAULT 1
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS versions (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        note TEXT,
        created_at TEXT,
        created_by TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS approvals (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        assigned_to TEXT NOT NULL,
        status TEXT NOT NULL,
        comment TEXT,
        created_at TEXT,
        decided_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS signatures (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        signer TEXT NOT NULL,
        method TEXT,
        image_path TEXT,
        signed_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS tickets (
        id TEXT PRIMARY KEY,
        requester TEXT NOT NULL,
        process_type TEXT NOT NULL,
        linked_document_id TEXT,
        status TEXT,
        priority TEXT,
        sla_hours INTEGER,
        notes TEXT,
        assigned_to TEXT,
        created_at TEXT,
        closed_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS audit (
        id TEXT PRIMARY KEY,
        entity TEXT,
        entity_id TEXT,
        action TEXT,
        actor TEXT,
        at TEXT,
        details TEXT
    )""")

    # NEW: Custom workflow tables
    cur.execute("""CREATE TABLE IF NOT EXISTS custom_workflows (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        trigger_conditions TEXT,  -- JSON: {doc_type: [], department: [], etc}
        created_by TEXT NOT NULL,
        created_at TEXT,
        active INTEGER DEFAULT 1,
        version INTEGER DEFAULT 1
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS workflow_steps (
        id TEXT PRIMARY KEY,
        workflow_id TEXT NOT NULL,
        step_order INTEGER NOT NULL,
        step_name TEXT NOT NULL,
        step_type TEXT NOT NULL,  -- review, approve, sign, annotate, verify, route
        assignee_type TEXT,       -- role, user, department, dynamic
        assignee_value TEXT,      -- specific role/user name or rule
        required BOOLEAN DEFAULT 1,
        instructions TEXT,
        sla_hours INTEGER DEFAULT 48,
        parallel_group INTEGER DEFAULT 0,  -- 0 = sequential, >0 = parallel group
        conditions TEXT,          -- JSON: conditions for this step
        FOREIGN KEY (workflow_id) REFERENCES custom_workflows(id)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS workflow_instances (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        workflow_id TEXT NOT NULL,
        current_step INTEGER DEFAULT 1,
        status TEXT DEFAULT 'active',  -- active, completed, cancelled
        started_at TEXT,
        completed_at TEXT,
        FOREIGN KEY (document_id) REFERENCES documents(id),
        FOREIGN KEY (workflow_id) REFERENCES custom_workflows(id)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS step_executions (
        id TEXT PRIMARY KEY,
        workflow_instance_id TEXT NOT NULL,
        step_id TEXT NOT NULL,
        assigned_to TEXT NOT NULL,
        status TEXT DEFAULT 'pending',  -- pending, in_progress, completed, skipped
        started_at TEXT,
        completed_at TEXT,
        result TEXT,              -- approved, rejected, signed, etc
        comments TEXT,
        attachments TEXT,         -- JSON: list of attachment paths
        FOREIGN KEY (workflow_instance_id) REFERENCES workflow_instances(id),
        FOREIGN KEY (step_id) REFERENCES workflow_steps(id)
    )""")

    # Document annotations and notes
    cur.execute("""CREATE TABLE IF NOT EXISTS document_annotations (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        author TEXT NOT NULL,
        annotation_type TEXT,    -- note, highlight, signature_request
        content TEXT,
        position_data TEXT,      -- JSON: page, coordinates, etc
        created_at TEXT,
        FOREIGN KEY (document_id) REFERENCES documents(id)
    )""")

    conn.commit()
    conn.close()

def seed_users():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    if (cur.fetchone() or [0])[0] == 0:
        cur.executemany("INSERT INTO users (id,name,email,role) VALUES (?,?,?,?)", SEED_USERS)
        conn.commit()
    conn.close()

def add_audit(entity: str, entity_id: str, action: str, actor: str, details: str = ""):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO audit (id, entity, entity_id, action, actor, at, details) VALUES (?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), entity, entity_id, action, actor, now_iso(), details)
    )
    conn.commit()
    conn.close()

# ============================================================
# Helper Functions
# ============================================================
def get_users() -> List[Tuple[str, str, str]]:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, name, role FROM users ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_user_by_name(name: str) -> Optional[Tuple[str, str, str]]:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, name, role FROM users WHERE name=?", (name,))
    row = cur.fetchone()
    conn.close()
    return row

# ============================================================
# Document Operations
# ============================================================
def create_document_record(title, department, doc_type, sensitivity, tags: List[str],
                           retention_policy, retention_years: int,
                           created_by, status="Draft",
                           effective_date: Optional[str]=None, expiry_date: Optional[str]=None,
                           description: str = "", workflow_type: str = "") -> str:
    doc_id = str(uuid.uuid4())
    conn = connect()
    cur = conn.cursor()
    cur.execute("""INSERT INTO documents
        (id, title, department, doc_type, sensitivity, tags, retention_policy, retention_years,
         status, effective_date, expiry_date, created_at, created_by, active)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
        (doc_id, title, department, doc_type, sensitivity, ",".join(tags),
         retention_policy, int(retention_years or 0), status,
         effective_date or "", expiry_date or "", now_iso(), created_by))
    conn.commit()
    conn.close()
    add_audit("document", doc_id, "create", created_by, f"{title} - {workflow_type}")
    return doc_id

def next_version(document_id: str) -> int:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT MAX(version) FROM versions WHERE document_id=?", (document_id,))
    v = cur.fetchone()[0]
    conn.close()
    return (v or 0) + 1

def save_upload(file, doc_id: str, version: int) -> str:
    name = f"{doc_id}_v{version}_{file.name}"
    path = os.path.join(FILES_DIR, name)
    with open(path, "wb") as f:
        f.write(file.getbuffer())
    return path

def add_version(document_id: str, version: int, file_path: str, created_by: str, note: str = ""):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""INSERT INTO versions
        (id, document_id, version, file_path, note, created_at, created_by)
        VALUES (?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), document_id, version, file_path, note, now_iso(), created_by))
    conn.commit()
    conn.close()
    add_audit("version", document_id, f"v{version}", created_by, note)

def list_documents(filters: dict):
    conn = connect()
    cur = conn.cursor()
    query = "SELECT id, title, department, doc_type, sensitivity, tags, status, created_at, created_by FROM documents WHERE 1=1"
    args = []
    if filters.get("q"):
        q = f"%{filters['q'].lower()}%"
        query += " AND (LOWER(title) LIKE ? OR LOWER(tags) LIKE ? OR LOWER(department) LIKE ? OR LOWER(doc_type) LIKE ?)"
        args += [q, q, q, q]
    if filters.get("department"):
        query += " AND department=?"; args.append(filters["department"])
    if filters.get("doc_type"):
        query += " AND doc_type=?"; args.append(filters["doc_type"])
    if filters.get("sensitivity"):
        query += " AND sensitivity=?"; args.append(filters["sensitivity"])
    if filters.get("status"):
        query += " AND status=?"; args.append(filters["status"])
    query += " ORDER BY created_at DESC"
    cur.execute(query, args)
    rows = cur.fetchall()
    conn.close()
    return rows

def list_versions(document_id: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT version, file_path, created_at, created_by, note FROM versions WHERE document_id=? ORDER BY version DESC", (document_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

# ============================================================
# Custom Workflow Management Functions
# ============================================================
def create_custom_workflow(name: str, description: str, trigger_conditions: Dict[str, Any], created_by: str) -> str:
    """Create a new custom workflow"""
    workflow_id = str(uuid.uuid4())
    conn = connect()
    cur = conn.cursor()
    cur.execute("""INSERT INTO custom_workflows 
        (id, name, description, trigger_conditions, created_by, created_at, active, version)
        VALUES (?,?,?,?,?,?,1,1)""",
        (workflow_id, name, description, json.dumps(trigger_conditions), created_by, now_iso()))
    conn.commit()
    conn.close()
    add_audit("workflow", workflow_id, "create", created_by, f"Custom workflow: {name}")
    return workflow_id

def add_workflow_step(workflow_id: str, step_order: int, step_name: str, step_type: str, 
                     assignee_type: str, assignee_value: str, required: bool = True,
                     instructions: str = "", sla_hours: int = 48, parallel_group: int = 0,
                     conditions: Dict[str, Any] = None) -> str:
    """Add a step to a custom workflow"""
    step_id = str(uuid.uuid4())
    conn = connect()
    cur = conn.cursor()
    cur.execute("""INSERT INTO workflow_steps 
        (id, workflow_id, step_order, step_name, step_type, assignee_type, assignee_value, 
         required, instructions, sla_hours, parallel_group, conditions)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (step_id, workflow_id, step_order, step_name, step_type, assignee_type, assignee_value,
         required, instructions, sla_hours, parallel_group, json.dumps(conditions or {})))
    conn.commit()
    conn.close()
    return step_id

def get_custom_workflows() -> List[Dict[str, Any]]:
    """Get all custom workflows"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT id, name, description, trigger_conditions, created_by, created_at, active
                   FROM custom_workflows WHERE active=1 ORDER BY name""")
    rows = cur.fetchall()
    conn.close()
    
    workflows = []
    for row in rows:
        workflows.append({
            "id": row[0], "name": row[1], "description": row[2],
            "trigger_conditions": json.loads(row[3]) if row[3] else {},
            "created_by": row[4], "created_at": row[5], "active": row[6]
        })
    return workflows

def get_workflow_steps(workflow_id: str) -> List[Dict[str, Any]]:
    """Get steps for a workflow"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT id, step_order, step_name, step_type, assignee_type, assignee_value,
                          required, instructions, sla_hours, parallel_group, conditions
                   FROM workflow_steps WHERE workflow_id=? ORDER BY step_order""", (workflow_id,))
    rows = cur.fetchall()
    conn.close()
    
    steps = []
    for row in rows:
        steps.append({
            "id": row[0], "step_order": row[1], "step_name": row[2], "step_type": row[3],
            "assignee_type": row[4], "assignee_value": row[5], "required": row[6],
            "instructions": row[7], "sla_hours": row[8], "parallel_group": row[9],
            "conditions": json.loads(row[10]) if row[10] else {}
        })
    return steps

def start_custom_workflow(document_id: str, workflow_id: str) -> str:
    """Start a custom workflow for a document"""
    instance_id = str(uuid.uuid4())
    conn = connect()
    cur = conn.cursor()
    
    # Create workflow instance
    cur.execute("""INSERT INTO workflow_instances 
        (id, document_id, workflow_id, current_step, status, started_at)
        VALUES (?,?,?,1,'active',?)""",
        (instance_id, document_id, workflow_id, now_iso()))
    
    # Create step executions for all steps
    steps = get_workflow_steps(workflow_id)
    for step in steps:
        # Determine assignee
        assignee = resolve_assignee(step["assignee_type"], step["assignee_value"], document_id)
        if assignee:
            status = "pending" if step["step_order"] == 1 else "waiting"
            cur.execute("""INSERT INTO step_executions 
                (id, workflow_instance_id, step_id, assigned_to, status)
                VALUES (?,?,?,?,?)""",
                (str(uuid.uuid4()), instance_id, step["id"], assignee, status))
    
    conn.commit()
    conn.close()
    return instance_id

def resolve_assignee(assignee_type: str, assignee_value: str, document_id: str) -> Optional[str]:
    """Resolve who should be assigned to a step"""
    if assignee_type == "user":
        # Direct user assignment
        user = get_user_by_name(assignee_value)
        return user[0] if user else None
    elif assignee_type == "role":
        # Find first user with this role
        users = get_users()
        for user in users:
            if user[2] == assignee_value:
                return user[0]
    elif assignee_type == "department":
        # Find department manager or lead
        users = get_users()
        for user in users:
            if "Manager" in user[2] or "Lead" in user[2]:
                return user[0]
    elif assignee_type == "dynamic":
        # Dynamic assignment based on document properties
        # Could implement various rules here
        pass
    
    return None

def check_workflow_triggers(document: Dict[str, Any]) -> List[str]:
    """Check which workflows should be triggered for a document"""
    workflows = get_custom_workflows()
    triggered_workflows = []
    
    for workflow in workflows:
        conditions = workflow["trigger_conditions"]
        should_trigger = True
        
        # Check document type condition
        if "doc_type" in conditions:
            if document["doc_type"] not in conditions["doc_type"]:
                should_trigger = False
        
        # Check department condition
        if "department" in conditions:
            if document["department"] not in conditions["department"]:
                should_trigger = False
        
        # Check sensitivity condition
        if "sensitivity" in conditions:
            if document["sensitivity"] not in conditions["sensitivity"]:
                should_trigger = False
        
        if should_trigger:
            triggered_workflows.append(workflow["id"])
    
    return triggered_workflows

def get_workflow_instance_status(document_id: str) -> Optional[Dict[str, Any]]:
    """Get the current workflow status for a document"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT wi.id, wi.workflow_id, wi.current_step, wi.status, wi.started_at,
                          cw.name as workflow_name
                   FROM workflow_instances wi
                   JOIN custom_workflows cw ON wi.workflow_id = cw.id
                   WHERE wi.document_id=? AND wi.status='active'""", (document_id,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        "instance_id": row[0], "workflow_id": row[1], "current_step": row[2],
        "status": row[3], "started_at": row[4], "workflow_name": row[5]
    }

def complete_workflow_step(instance_id: str, step_id: str, result: str, comments: str, user_id: str):
    """Complete a workflow step"""
    conn = connect()
    cur = conn.cursor()
    
    # Update step execution
    cur.execute("""UPDATE step_executions 
                   SET status='completed', completed_at=?, result=?, comments=?
                   WHERE workflow_instance_id=? AND step_id=? AND assigned_to=?""",
                (now_iso(), result, comments, instance_id, step_id, user_id))
    
    # Check if we should advance workflow
    cur.execute("""SELECT COUNT(*) FROM step_executions se
                   JOIN workflow_steps ws ON se.step_id = ws.id
                   WHERE se.workflow_instance_id=? AND ws.required=1 AND se.status != 'completed'""",
                (instance_id,))
    
    remaining_required = cur.fetchone()[0]
    
    if remaining_required == 0:
        # Workflow complete
        cur.execute("""UPDATE workflow_instances 
                       SET status='completed', completed_at=? WHERE id=?""",
                    (now_iso(), instance_id))
        
        # Update document status
        cur.execute("""SELECT document_id FROM workflow_instances WHERE id=?""", (instance_id,))
        doc_id = cur.fetchone()[0]
        if result == "approved":
            cur.execute("UPDATE documents SET status='Approved' WHERE id=?", (doc_id,))
        elif result == "rejected":
            cur.execute("UPDATE documents SET status='Rejected' WHERE id=?", (doc_id,))
    
    conn.commit()
    conn.close()

def add_document_annotation(document_id: str, version: int, author: str, 
                          annotation_type: str, content: str, position_data: Dict[str, Any] = None):
    """Add an annotation to a document"""
    annotation_id = str(uuid.uuid4())
    conn = connect()
    cur = conn.cursor()
    cur.execute("""INSERT INTO document_annotations 
        (id, document_id, version, author, annotation_type, content, position_data, created_at)
        VALUES (?,?,?,?,?,?,?,?)""",
        (annotation_id, document_id, version, author, annotation_type, content,
         json.dumps(position_data or {}), now_iso()))
    conn.commit()
    conn.close()
    return annotation_id

def get_document_annotations(document_id: str, version: int = None) -> List[Dict[str, Any]]:
    """Get annotations for a document"""
    conn = connect()
    cur = conn.cursor()
    
    if version:
        cur.execute("""SELECT id, version, author, annotation_type, content, position_data, created_at
                       FROM document_annotations 
                       WHERE document_id=? AND version=? ORDER BY created_at""", 
                    (document_id, version))
    else:
        cur.execute("""SELECT id, version, author, annotation_type, content, position_data, created_at
                       FROM document_annotations 
                       WHERE document_id=? ORDER BY version DESC, created_at""", 
                    (document_id,))
    
    rows = cur.fetchall()
    conn.close()
    
    annotations = []
    for row in rows:
        annotations.append({
            "id": row[0], "version": row[1], "author": row[2], "annotation_type": row[3],
            "content": row[4], "position_data": json.loads(row[5]) if row[5] else {},
            "created_at": row[6]
        })
    return annotations
def create_sequential_approvals(document_id: str, workflow_type: str, created_by: str):
    if workflow_type not in APPROVAL_WORKFLOWS:
        return False
    
    workflow = APPROVAL_WORKFLOWS[workflow_type]
    conn = connect()
    cur = conn.cursor()
    
    # Clear any existing approvals for this document
    cur.execute("DELETE FROM approvals WHERE document_id=?", (document_id,))
    
    # Create approval steps - first one pending, rest queued
    for i, role_name in enumerate(workflow["steps"]):
        # Find user with this role
        user = get_user_by_name(role_name)
        if not user:
            # Fallback: find any user with this role
            users = get_users()
            matching_users = [u for u in users if u[2] == role_name]
            if matching_users:
                user = matching_users[0]
        
        if user:
            status = "pending" if i == 0 else "queued"
            cur.execute("""INSERT INTO approvals
                (id, document_id, assigned_to, status, comment, created_at, decided_at)
                VALUES (?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), document_id, user[0], status, "", now_iso(), ""))
    
    conn.commit()
    conn.close()
    add_audit("workflow", document_id, "create", created_by, f"Workflow: {workflow_type}")
    return True

def get_document_approvals(document_id: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT a.id, a.assigned_to, a.status, a.comment, a.created_at, a.decided_at,
                          u.name, u.role
                   FROM approvals a 
                   JOIN users u ON a.assigned_to = u.id
                   WHERE a.document_id=? 
                   ORDER BY a.created_at""", (document_id,))
    rows = cur.fetchall()
    conn.close()
    
    approvals = []
    for row in rows:
        approvals.append({
            "id": row[0], "assigned_to": row[1], "status": row[2], "comment": row[3],
            "created_at": row[4], "decided_at": row[5], "user_name": row[6], "user_role": row[7]
        })
    return approvals

def assign_approval(document_id: str, approver_id: str, status: str = "pending"):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""INSERT INTO approvals
        (id, document_id, assigned_to, status, comment, created_at, decided_at)
        VALUES (?,?,?,?,?, ?, '')""",
        (str(uuid.uuid4()), document_id, approver_id, status, "", now_iso()))
    conn.commit()
    conn.close()
    add_audit("approval", document_id, status, approver_id, "")

def decide_approval(document_id: str, approver_id: str, decision: str, comment: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""UPDATE approvals
       SET status=?, comment=?, decided_at=?
       WHERE document_id=? AND assigned_to=? AND status='pending'""",
       (decision, comment, now_iso(), document_id, approver_id))
    
    # If approved, promote next queued approver
    if decision == "approved":
        cur.execute("SELECT id FROM approvals WHERE document_id=? AND status='queued' ORDER BY created_at ASC LIMIT 1", (document_id,))
        nxt = cur.fetchone()
        if nxt:
            cur.execute("UPDATE approvals SET status='pending' WHERE id=?", (nxt[0],))
        else:
            # All approvals complete
            cur.execute("UPDATE documents SET status='Approved' WHERE id=?", (document_id,))
    elif decision == "rejected":
        # Mark document as rejected
        cur.execute("UPDATE documents SET status='Rejected' WHERE id=?", (document_id,))
        cur.execute("UPDATE approvals SET status='skipped' WHERE document_id=? AND status='queued'", (document_id,))
    
    conn.commit()
    conn.close()
    add_audit("approval", document_id, decision, approver_id, comment)

# ============================================================
# E-Signatures
# ============================================================
def add_signature_image(text: str) -> Image.Image:
    img = Image.new("RGB", (600, 200), "white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 80), text, fill="black")
    return img

def save_signature(document_id: str, signer_id: str, method: str, image: Optional[Image.Image] = None):
    path = None
    if image is not None:
        path = os.path.join(FILES_DIR, f"sig_{document_id}_{uuid.uuid4().hex}.png")
        image.save(path)
    conn = connect()
    cur = conn.cursor()
    cur.execute("""INSERT INTO signatures
        (id, document_id, signer, method, image_path, signed_at)
        VALUES (?,?,?,?,?,?)""",
        (str(uuid.uuid4()), document_id, signer_id, method, path, now_iso()))
    conn.commit()
    conn.close()
    add_audit("signature", document_id, method, signer_id, path or "")

# ============================================================
# Tickets
# ============================================================
def create_ticket(requester_id: str, process_type: str, linked_document_id: str, notes: str,
                  priority: str = "Normal", sla_hours: int = 48, assigned_to: str = "") -> str:
    tid = str(uuid.uuid4())
    conn = connect()
    cur = conn.cursor()
    cur.execute("""INSERT INTO tickets
        (id, requester, process_type, linked_document_id, status, priority, sla_hours, notes, assigned_to, created_at, closed_at)
        VALUES (?,?,?,?, 'Open', ?, ?, ?, ?, ?, '')""",
        (tid, requester_id, process_type, linked_document_id, priority, sla_hours, notes, assigned_to, now_iso()))
    conn.commit()
    conn.close()
    add_audit("ticket", tid, "create", requester_id, f"{process_type} -> {linked_document_id}")
    return tid

def list_my_tickets(user_id: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT id, process_type, status, priority, sla_hours, notes, linked_document_id, created_at
                   FROM tickets
                   WHERE requester=? OR assigned_to=?
                   ORDER BY created_at DESC""", (user_id, user_id))
    rows = cur.fetchall()
    conn.close()
    return rows

def close_ticket(ticket_id: str, user_id: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET status='Closed', closed_at=? WHERE id=?", (now_iso(), ticket_id))
    conn.commit()
    conn.close()
    add_audit("ticket", ticket_id, "close", user_id, "")

# ============================================================
# UI PAGES - Enhanced with Workflow Builder
# ============================================================
def page_workflow_builder(current_user):
    """Custom workflow builder interface"""
    st.subheader("🔧 Custom Workflow Builder")
    
    if current_user[2] not in ["Admin", "VP", "Director"]:
        st.error("Access denied. Only admins and senior managers can create custom workflows.")
        return
    
    tab1, tab2, tab3 = st.tabs(["➕ Create Workflow", "📋 Manage Workflows", "📊 Analytics"])
    
    with tab1:
        st.markdown("### Create New Workflow")
        
        with st.form("workflow_builder"):
            # Basic workflow info
            col1, col2 = st.columns(2)
            with col1:
                workflow_name = st.text_input("Workflow Name *", placeholder="e.g., Vendor Contract Review")
                description = st.text_area("Description", height=100, 
                                         placeholder="Describe what this workflow is for and when it should be used")
            
            with col2:
                st.markdown("**Trigger Conditions**")
                trigger_doc_types = st.multiselect("Document Types", DOCUMENT_TYPES)
                trigger_departments = st.multiselect("Departments", DEPARTMENTS)
                trigger_sensitivity = st.multiselect("Sensitivity Levels", SENSITIVITY)
            
            # Workflow steps builder
            st.markdown("### 🔄 Workflow Steps")
            st.info("Define the steps for this workflow. Steps will execute in order unless marked as parallel.")
            
            if "workflow_steps" not in st.session_state:
                st.session_state.workflow_steps = []
            
            # Add step interface
            with st.expander("➕ Add New Step", expanded=len(st.session_state.workflow_steps) == 0):
                step_col1, step_col2, step_col3 = st.columns(3)
                
                with step_col1:
                    step_name = st.text_input("Step Name", placeholder="e.g., Legal Review")
                    step_type = st.selectbox("Step Type", list(STEP_ACTIONS.keys()), 
                                           format_func=lambda x: STEP_ACTIONS[x])
                    required = st.checkbox("Required Step", value=True)
                
                with step_col2:
                    assignee_type = st.selectbox("Assign To", ["role", "user", "department"])
                    
                    if assignee_type == "role":
                        assignee_options = ["Admin", "VP", "Director", "Department Manager", 
                                          "Engineering Manager", "Finance Manager", "Legal Counsel",
                                          "Engineering Lead", "QA Reviewer", "Approver"]
                        assignee_value = st.selectbox("Role", assignee_options)
                    elif assignee_type == "user":
                        users = get_users()
                        user_options = [u[1] for u in users]
                        assignee_value = st.selectbox("User", user_options)
                    else:
                        assignee_value = st.selectbox("Department", DEPARTMENTS)
                
                with step_col3:
                    sla_hours = st.number_input("SLA (hours)", 1, 720, 48)
                    parallel_group = st.number_input("Parallel Group (0=sequential)", 0, 10, 0,
                                                   help="Steps with same group number run in parallel")
                
                instructions = st.text_area("Instructions for Assignee", height=80,
                                          placeholder="Detailed instructions for what the assignee should do...")
                
                if st.button("➕ Add Step"):
                    step = {
                        "step_name": step_name,
                        "step_type": step_type,
                        "assignee_type": assignee_type,
                        "assignee_value": assignee_value,
                        "required": required,
                        "instructions": instructions,
                        "sla_hours": sla_hours,
                        "parallel_group": parallel_group
                    }
                    st.session_state.workflow_steps.append(step)
                    st.success(f"Added step: {step_name}")
                    st.rerun()
            
            # Display current steps
            if st.session_state.workflow_steps:
                st.markdown("#### Current Workflow Steps")
                for i, step in enumerate(st.session_state.workflow_steps):
                    with st.container():
                        col1, col2, col3, col4 = st.columns([1, 3, 2, 1])
                        
                        with col1:
                            st.write(f"**Step {i+1}**")
                            if step["parallel_group"] > 0:
                                st.caption(f"Parallel Group {step['parallel_group']}")
                        
                        with col2:
                            st.write(f"**{step['step_name']}**")
                            st.caption(f"{STEP_ACTIONS[step['step_type']]} • {step['assignee_type']}: {step['assignee_value']}")
                        
                        with col3:
                            required_text = "Required" if step["required"] else "Optional"
                            st.write(f"{required_text} • {step['sla_hours']}h SLA")
                        
                        with col4:
                            if st.button("🗑️", key=f"delete_step_{i}", help="Delete step"):
                                st.session_state.workflow_steps.pop(i)
                                st.rerun()
                        
                        if step["instructions"]:
                            st.caption(f"Instructions: {step['instructions'][:100]}...")
                        
                        st.divider()
            
            # Create workflow button
            submitted = st.form_submit_button("🚀 Create Workflow", type="primary")
            
            if submitted:
                if not workflow_name or not st.session_state.workflow_steps:
                    st.error("Please provide a workflow name and at least one step.")
                    return
                
                # Create workflow
                trigger_conditions = {
                    "doc_type": trigger_doc_types,
                    "department": trigger_departments,
                    "sensitivity": trigger_sensitivity
                }
                
                workflow_id = create_custom_workflow(workflow_name, description, trigger_conditions, current_user[0])
                
                # Add steps
                for i, step in enumerate(st.session_state.workflow_steps):
                    add_workflow_step(
                        workflow_id=workflow_id,
                        step_order=i + 1,
                        step_name=step["step_name"],
                        step_type=step["step_type"],
                        assignee_type=step["assignee_type"],
                        assignee_value=step["assignee_value"],
                        required=step["required"],
                        instructions=step["instructions"],
                        sla_hours=step["sla_hours"],
                        parallel_group=step["parallel_group"]
                    )
                
                st.success(f"Workflow '{workflow_name}' created successfully!")
                st.session_state.workflow_steps = []  # Clear the form
                add_audit("workflow", workflow_id, "create", current_user[0], f"Created workflow: {workflow_name}")
                st.rerun()
    
    with tab2:
        st.markdown("### Existing Custom Workflows")
        
        workflows = get_custom_workflows()
        
        if not workflows:
            st.info("No custom workflows created yet. Use the 'Create Workflow' tab to build your first workflow.")
        else:
            for workflow in workflows:
                with st.expander(f"🔧 {workflow['name']}", expanded=False):
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.write(f"**Description:** {workflow['description']}")
                        st.write(f"**Created by:** {workflow['created_by']} on {workflow['created_at'][:10]}")
                        
                        # Show trigger conditions
                        conditions = workflow['trigger_conditions']
                        if any(conditions.values()):
                            st.write("**Triggers when:**")
                            if conditions.get('doc_type'):
                                st.write(f"• Document type: {', '.join(conditions['doc_type'])}")
                            if conditions.get('department'):
                                st.write(f"• Department: {', '.join(conditions['department'])}")
                            if conditions.get('sensitivity'):
                                st.write(f"• Sensitivity: {', '.join(conditions['sensitivity'])}")
                    
                    with col2:
                        if st.button("📋 View Steps", key=f"view_{workflow['id']}"):
                            st.session_state.selected_workflow = workflow['id']
                        
                        if st.button("🗑️ Deactivate", key=f"deactivate_{workflow['id']}"):
                            # In a real system, you'd deactivate rather than delete
                            st.warning("Workflow deactivation would be implemented here")
                    
                    # Show workflow steps if selected
                    if st.session_state.get('selected_workflow') == workflow['id']:
                        st.markdown("#### Workflow Steps")
                        steps = get_workflow_steps(workflow['id'])
                        
                        for step in steps:
                            step_col1, step_col2, step_col3 = st.columns([1, 2, 1])
                            
                            with step_col1:
                                st.write(f"**Step {step['step_order']}**")
                                if step['parallel_group'] > 0:
                                    st.caption(f"Parallel Group {step['parallel_group']}")
                            
                            with step_col2:
                                st.write(f"**{step['step_name']}**")
                                st.caption(f"{STEP_ACTIONS[step['step_type']]} → {step['assignee_value']}")
                                if step['instructions']:
                                    st.caption(f"Instructions: {step['instructions'][:80]}...")
                            
                            with step_col3:
                                required_text = "✅ Required" if step['required'] else "⚪ Optional"
                                st.write(required_text)
                                st.caption(f"{step['sla_hours']}h SLA")
    
    with tab3:
        st.markdown("### Workflow Analytics")
        
        # Get workflow usage stats
        conn = connect()
        cur = conn.cursor()
        
        # Workflow execution counts
        cur.execute("""SELECT cw.name, COUNT(wi.id) as executions
                       FROM custom_workflows cw
                       LEFT JOIN workflow_instances wi ON cw.id = wi.workflow_id
                       WHERE cw.active = 1
                       GROUP BY cw.id, cw.name
                       ORDER BY executions DESC""")
        
        workflow_stats = cur.fetchall()
        conn.close()
        
        if workflow_stats:
            st.markdown("#### Workflow Usage")
            for workflow_name, count in workflow_stats:
                st.metric(workflow_name, f"{count} executions")
        else:
            st.info("No workflow execution data available yet.")

def page_enhanced_document_viewer(current_user):
    """Enhanced document viewer with annotations and workflow status"""
    st.subheader("📋 Enhanced Document Viewer")
    
    # Document selection
    col1, col2 = st.columns([2, 1])
    with col1:
        doc_id = st.text_input("🔍 Enter Document ID", 
                              value=st.session_state.get("selected_doc_id", ""),
                              placeholder="Document ID...")
    with col2:
        if st.button("🔄 Refresh", type="secondary"):
            st.rerun()
    
    if not doc_id:
        st.info("Enter a document ID above to view details, workflow status, and add annotations.")
        return
    
    # Store selected doc ID
    st.session_state.selected_doc_id = doc_id
    
    # Get document details
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT id, title, department, doc_type, sensitivity, tags, status, 
                          created_at, created_by FROM documents WHERE id=? AND active=1""", (doc_id,))
    doc_row = cur.fetchone()
    conn.close()
    
    if not doc_row:
        st.error("❌ Document not found.")
        return
    
    doc = {
        "id": doc_row[0], "title": doc_row[1], "department": doc_row[2], 
        "doc_type": doc_row[3], "sensitivity": doc_row[4], "tags": doc_row[5],
        "status": doc_row[6], "created_at": doc_row[7], "created_by": doc_row[8]
    }
    
    # Document header
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.markdown(f"## {doc['title']}")
        st.write(f"**Department:** {doc['department']} • **Type:** {doc['doc_type']}")
    with col2:
        status_colors = {"Draft": "🟡", "Review": "🔵", "Approved": "🟢", "Rejected": "🔴"}
        status_icon = status_colors.get(doc['status'], '⚫')
        st.markdown(f"### {status_icon} {doc['status']}")
    with col3:
        st.write(f"**Created:** {doc['created_at'][:10]}")
        st.write(f"**Sensitivity:** {doc['sensitivity']}")
    
    # Tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["📄 Document & Versions", "🔄 Workflow Status", "📝 Annotations", "✍️ Add Notes"])
    
    with tab1:
        # Document versions
        versions = list_versions(doc_id)
        
        if not versions:
            st.warning("No versions found for this document.")
        else:
            selected_version_idx = st.selectbox("Select version:", 
                                               range(len(versions)), 
                                               format_func=lambda x: f"v{versions[x][0]} - {versions[x][2][:16]}")
            
            selected_version = versions[selected_version_idx]
            version_num, file_path, created_at, created_by, note = selected_version
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**Version:** {version_num}")
                st.write(f"**Created:** {created_at[:16]}")
            with col2:
                st.write(f"**Author:** {created_by}")
                if note:
                    st.write(f"**Note:** {note}")
            with col3:
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        st.download_button("📥 Download", data=f.read(), 
                                         file_name=os.path.basename(file_path))
                
                # Simple file preview placeholder
                st.info("📄 Document preview would be displayed here")
                # In a real system, you'd integrate document preview here
    
    with tab2:
        # Workflow status
        workflow_status = get_workflow_instance_status(doc_id)
        
        if workflow_status:
            st.markdown(f"### 🔄 Active Workflow: {workflow_status['workflow_name']}")
            st.write(f"**Started:** {workflow_status['started_at'][:16]}")
            st.write(f"**Current Step:** {workflow_status['current_step']}")
            
            # Get current step executions
            conn = connect()
            cur = conn.cursor()
            cur.execute("""SELECT se.id, ws.step_name, ws.step_type, se.assigned_to, se.status, 
                                  se.started_at, se.result, se.comments, u.name
                           FROM step_executions se
                           JOIN workflow_steps ws ON se.step_id = ws.id
                           JOIN users u ON se.assigned_to = u.id
                           WHERE se.workflow_instance_id = ?
                           ORDER BY ws.step_order""", (workflow_status['instance_id'],))
            step_executions = cur.fetchall()
            conn.close()
            
            if step_executions:
                st.markdown("#### Workflow Progress")
                for execution in step_executions:
                    step_col1, step_col2, step_col3, step_col4 = st.columns([2, 2, 1, 2])
                    
                    with step_col1:
                        st.write(f"**{execution[1]}**")  # step_name
                        st.caption(STEP_ACTIONS.get(execution[2], execution[2]))  # step_type
                    
                    with step_col2:
                        st.write(f"**Assignee:** {execution[8]}")  # user name
                    
                    with step_col3:
                        status = execution[4]
                        if status == "completed":
                            st.success("✅ Done")
                        elif status == "pending":
                            st.warning("⏳ Pending")
                        else:
                            st.info("⏸️ Waiting")
                    
                    with step_col4:
                        if execution[6]:  # result
                            st.write(f"**Result:** {execution[6]}")
                        if execution[7]:  # comments
                            st.caption(f"Comments: {execution[7][:50]}...")
                
                # Action buttons for current user
                user_pending_steps = [e for e in step_executions 
                                    if e[3] == current_user[0] and e[4] == "pending"]
                
                if user_pending_steps:
                    st.markdown("#### Your Pending Actions")
                    for execution in user_pending_steps:
                        step_name = execution[1]
                        step_type = execution[2]
                        
                        st.write(f"**Action Required:** {step_name}")
                        
                        if step_type == "approve":
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("✅ Approve", key=f"approve_{execution[0]}"):
                                    complete_workflow_step(workflow_status['instance_id'], 
                                                         execution[0], "approved", "", current_user[0])
                                    st.success("Step approved!")
                                    st.rerun()
                            with col2:
                                if st.button("❌ Reject", key=f"reject_{execution[0]}"):
                                    complete_workflow_step(workflow_status['instance_id'], 
                                                         execution[0], "rejected", "", current_user[0])
                                    st.error("Step rejected!")
                                    st.rerun()
                        
                        elif step_type == "sign":
                            signature_text = st.text_input("Type your name to sign:", key=f"sign_{execution[0]}")
                            if st.button("✍️ Sign", key=f"btn_sign_{execution[0]}") and signature_text:
                                # Create signature
                                img = add_signature_image(signature_text)
                                save_signature(doc_id, current_user[0], "typed", img)
                                complete_workflow_step(workflow_status['instance_id'], 
                                                     execution[0], "signed", f"Signed as: {signature_text}", current_user[0])
                                st.success("Document signed!")
                                st.rerun()
                        
                        elif step_type == "review":
                            review_comments = st.text_area("Review comments:", key=f"review_{execution[0]}")
                            if st.button("📝 Complete Review", key=f"btn_review_{execution[0]}"):
                                complete_workflow_step(workflow_status['instance_id'], 
                                                     execution[0], "reviewed", review_comments, current_user[0])
                                st.success("Review completed!")
                                st.rerun()
        else:
            # Check for legacy approvals
            approvals = get_document_approvals(doc_id)
            if approvals:
                st.markdown("### Legacy Approval Workflow")
                for approval in approvals:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write(f"**{approval['user_name']}**")
                    with col2:
                        if approval["status"] == "approved":
                            st.success("✅ Approved")
                        elif approval["status"] == "rejected":
                            st.error("❌ Rejected")
                        elif approval["status"] == "pending":
                            st.warning("⏳ Pending")
                        else:
                            st.info("⏸️ Queued")
                    with col3:
                        if approval["comment"]:
                            st.caption(approval["comment"])
            else:
                st.info("No active workflow for this document.")
    
    with tab3:
        # Document annotations
        st.markdown("### 📝 Document Annotations")
        
        versions = list_versions(doc_id)
        if versions:
            version_for_annotations = st.selectbox("View annotations for version:", 
                                                   [v[0] for v in versions],
                                                   format_func=lambda x: f"Version {x}")
            
            annotations = get_document_annotations(doc_id, version_for_annotations)
            
            if annotations:
                for annotation in annotations:
                    with st.container():
                        col1, col2, col3 = st.columns([2, 1, 1])
                        with col1:
                            st.write(f"**{annotation['annotation_type'].title()}** by {annotation['author']}")
                            st.write(annotation['content'])
                        with col2:
                            st.caption(f"Version {annotation['version']}")
                        with col3:
                            st.caption(annotation['created_at'][:16])
                        st.divider()
            else:
                st.info("No annotations for this version.")
    
    with tab4:
        # Add annotations
        st.markdown("### ✍️ Add Notes & Annotations")
        
        versions = list_versions(doc_id)
        if versions:
            target_version = st.selectbox("Add annotation to version:", 
                                        [v[0] for v in versions],
                                        format_func=lambda x: f"Version {x}")
            
            annotation_type = st.selectbox("Annotation Type", 
                                         ["note", "highlight", "signature_request", "change_request"])
            
            content = st.text_area("Content", height=120, 
                                 placeholder="Enter your note, comment, or request...")
            
            if st.button("💾 Save Annotation"):
                if content.strip():
                    add_document_annotation(doc_id, target_version, current_user[0], 
                                          annotation_type, content.strip())
                    st.success("Annotation added!")
                    st.rerun()
                else:
                    st.error("Please enter some content for the annotation.")
        else:
            st.warning("No document versions available for annotation.")
def page_create_document_enhanced(current_user):
    st.subheader("Create New Document")
    
    with st.form("create_document_form"):
        st.markdown("### Basic Information")
        col1, col2 = st.columns(2)
        
        with col1:
            title = st.text_input("Document Title *", help="Clear, descriptive title")
            department = st.selectbox("Department *", DEPARTMENTS)
            doc_type = st.selectbox("Document Type *", DOCUMENT_TYPES)
        
        with col2:
            sensitivity = st.selectbox("Sensitivity Level", SENSITIVITY, index=1)
            retention_policy = st.selectbox("Retention Policy", list(RETENTION_POLICIES.keys()))
            retention_years = 0
            if retention_policy == "Custom":
                retention_years = st.number_input("Custom retention (years)", 1, 50, 5)
        
        description = st.text_area("Description", height=100)
        tags = st.text_input("Tags (comma-separated)", placeholder="policy, procedure, contract, etc.")
        
        st.markdown("### Approval Workflow")
        workflow_type = st.selectbox("Choose Approval Workflow *", list(APPROVAL_WORKFLOWS.keys()))
        
        if workflow_type:
            workflow = APPROVAL_WORKFLOWS[workflow_type]
            st.info(f"**{workflow['description']}**")
            st.write("Approval steps:")
            for i, step in enumerate(workflow['steps'], 1):
                st.write(f"  {i}. {step}")
        
        st.markdown("### File Upload")
        uploaded_file = st.file_uploader("Select document file *")
        version_note = st.text_area("Version Notes", height=80)
        
        st.markdown("### Dates")
        col1, col2 = st.columns(2)
        with col1:
            effective_date = st.date_input("Effective Date")
        with col2:
            expiry_date = st.date_input("Expiry Date")
        
        submitted = st.form_submit_button("Create Document & Start Approval", type="primary")
    
    if submitted:
        if not title or not uploaded_file or not workflow_type:
            st.error("Please fill in all required fields (marked with *)")
            return
        
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        doc_id = create_document_record(
            title=title,
            department=department,
            doc_type=doc_type,
            sensitivity=sensitivity,
            tags=tag_list,
            retention_policy=retention_policy,
            retention_years=int(retention_years or 0),
            created_by=current_user[0],
            status="Review",
            effective_date=effective_date.isoformat() if effective_date else None,
            expiry_date=expiry_date.isoformat() if expiry_date else None,
            description=description,
            workflow_type=workflow_type
        )
        
        version = next_version(doc_id)
        file_path = save_upload(uploaded_file, doc_id, version)
        add_version(doc_id, version, file_path, current_user[0], version_note)
        
        if create_sequential_approvals(doc_id, workflow_type, current_user[0]):
            st.success(f"Document created successfully!")
            st.info(f"Document ID: `{doc_id}`")
            st.info(f"Approval workflow '{workflow_type}' has been initiated")
            
            approvals = get_document_approvals(doc_id)
            pending_approvals = [a for a in approvals if a["status"] == "pending"]
            if pending_approvals:
                st.write("**Initial Approvers Assigned:**")
                for approval in pending_approvals:
                    st.write(f"• {approval['user_name']} ({approval['user_role']})")
        else:
            st.error("Failed to create approval workflow.")

def page_my_approvals_enhanced(current_user):
    st.subheader("My Pending Approvals")
    
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""SELECT a.document_id, d.title, d.doc_type, d.department, d.sensitivity,
                          a.status, a.comment, a.created_at, d.created_by, u.name as creator_name
                   FROM approvals a 
                   JOIN documents d ON a.document_id = d.id
                   JOIN users u ON d.created_by = u.id
                   WHERE a.assigned_to=? AND a.status='pending'
                   ORDER BY a.created_at ASC""", (current_user[0],))
    pending = cur.fetchall()
    
    cur.execute("""SELECT a.document_id, d.title, a.status, a.decided_at, a.comment
                   FROM approvals a 
                   JOIN documents d ON a.document_id = d.id
                   WHERE a.assigned_to=? AND a.status IN ('approved', 'rejected')
                   ORDER BY a.decided_at DESC LIMIT 10""", (current_user[0],))
    completed = cur.fetchall()
    conn.close()
    
    if not pending:
        st.success("No pending approvals!")
    else:
        st.write(f"You have **{len(pending)}** documents awaiting your approval:")
        
        for i, (doc_id, title, doc_type, dept, sens, status, comment, created_at, creator_id, creator_name) in enumerate(pending):
            with st.expander(f"{title} — {doc_type} · {dept}", expanded=True):
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.write(f"**Creator:** {creator_name}")
                    st.write(f"**Type:** {doc_type}")
                    st.write(f"**Sensitivity:** {sens}")
                with col2:
                    st.write(f"**Department:** {dept}")
                    st.write(f"**Created:** {created_at[:10]}")
                with col3:
                    versions = list_versions(doc_id)
                    if versions:
                        latest_version = versions[0]
                        version_num, file_path, _, _, _ = latest_version
                        if os.path.exists(file_path):
                            with open(file_path, "rb") as f:
                                st.download_button(
                                    f"Download v{version_num}",
                                    data=f.read(),
                                    file_name=os.path.basename(file_path),
                                    key=f"download_{i}"
                                )
                
                approvals = get_document_approvals(doc_id)
                st.write("**Approval Progress:**")
                
                progress_text = []
                for j, approval in enumerate(approvals):
                    if approval["status"] == "approved":
                        progress_text.append(f"✅ {approval['user_name']}")
                    elif approval["status"] == "rejected":
                        progress_text.append(f"❌ {approval['user_name']}")
                    elif approval["status"] == "pending":
                        progress_text.append(f"⏳ {approval['user_name']} (YOU)")
                    else:
                        progress_text.append(f"⏸️ {approval['user_name']}")
                
                st.write(" → ".join(progress_text))
                
                st.markdown("---")
                decision_col1, decision_col2 = st.columns([2, 1])
                with decision_col1:
                    decision_comment = st.text_area(
                        "Comments (optional)", 
                        key=f"comment_{i}",
                        height=80,
                        placeholder="Add your comments..."
                    )
                
                with decision_col2:
                    st.write("**Make Decision:**")
                    col_approve, col_reject = st.columns(2)
                    
                    with col_approve:
                        if st.button("✅ Approve", key=f"approve_{i}", type="primary"):
                            decide_approval(doc_id, current_user[0], "approved", decision_comment)
                            st.success("Document approved!")
                            st.rerun()
                    
                    with col_reject:
                        if st.button("❌ Reject", key=f"reject_{i}"):
                            if decision_comment.strip():
                                decide_approval(doc_id, current_user[0], "rejected", decision_comment)
                                st.error("Document rejected.")
                                st.rerun()
                            else:
                                st.error("Please provide a reason for rejection.")
    
    if completed:
        st.markdown("---")
        st.subheader("Recent Decisions")
        for doc_id, title, status, decided_at, comment in completed[:5]:
            status_icon = "✅" if status == "approved" else "❌"
            with st.expander(f"{status_icon} {title} — {status.title()}", expanded=False):
                st.write(f"**Decided:** {decided_at}")
                if comment:
                    st.write(f"**Comment:** {comment}")

def page_upload(current_user):
    st.subheader("Upload Document")
    title = st.text_input("Title *")
    department = st.selectbox("Department *", DEPARTMENTS)
    doc_type = st.selectbox("Document Type *", DOCUMENT_TYPES)
    sensitivity = st.selectbox("Sensitivity", SENSITIVITY, index=1)
    tags = st.text_input("Tags (comma-separated)")
    retention_policy = st.selectbox("Retention Policy", list(RETENTION_POLICIES.keys()))
    retention_years = 0
    if retention_policy == "Custom":
        retention_years = st.number_input("Custom retention (years)", 1, 50, 3)
    file = st.file_uploader("Select file *")
    note = st.text_area("Version note", height=80)

    if st.button("Save"):
        if not (title and file):
            st.error("Please provide a title and choose a file.")
            return
        doc_id = create_document_record(title, department, doc_type, sensitivity,
                                        [t.strip() for t in tags.split(",") if t.strip()],
                                        retention_policy, int(retention_years or 0),
                                        current_user[0], status="Draft")
        v = next_version(doc_id)
        path = save_upload(file, doc_id, v)
        add_version(doc_id, v, path, current_user[0], note)
        st.success(f"Uploaded v{v} for '{title}'.")

def page_browse(current_user):
    st.subheader("Search & Browse")
    with st.form("search_form"):
        q = st.text_input("Keyword search")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            dept = st.selectbox("Department", [""] + DEPARTMENTS)
        with c2:
            dtype = st.selectbox("Document Type", [""] + DOCUMENT_TYPES)
        with c3:
            sens = st.selectbox("Sensitivity", [""] + SENSITIVITY)
        with c4:
            stat = st.selectbox("Status", ["", "Draft", "Review", "Approved", "Executed"])
        submitted = st.form_submit_button("Apply filters")

    rows = list_documents({"q": q, "department": dept or None, "doc_type": dtype or None,
                           "sensitivity": sens or None, "status": stat or None})
    if not rows:
        st.info("No documents found.")
    for ridx, r in enumerate(rows):
        did, title, dept, dtype, sens, tags, status, created_at, created_by = r
        with st.expander(f"{title} — {dtype} · {dept} · {sens} · {status}"):
            st.caption(f"Created {created_at} by {created_by} • tags: {tags or '-'}")

            versions = list_versions(did)
            st.write("**Versions**")
            for v, path, cat, cby, note in versions:
                cols = st.columns([1, 2, 2, 2, 3])
                cols[0].markdown(f"**v{v}**")
                cols[1].markdown(cat)
                cols[2].markdown(cby)
                if os.path.exists(path):
                    with open(path, "rb") as fh:
                        cols[3].download_button("Download", file_name=os.path.basename(path), data=fh.read(), key=f"dl_{ridx}_{v}")
                cols[4].markdown(note or "")

            st.divider()
            st.markdown("**Workflow**")
            users = get_users()
            approver_names = [u[1] for u in users if u[2] == "Approver"]
            if approver_names:
                sel = st.selectbox("Assign approver", [""] + approver_names, key=f"sel_{ridx}")
                if st.button("Assign", key=f"assign_{ridx}") and sel:
                    uid = get_user_by_name(sel)[0]
                    assign_approval(did, uid, status="pending")
                    st.success("Approval assigned.")

            st.markdown("**E-Signature**")
            sig_name = st.text_input("Type your name to sign", key=f"sign_{ridx}")
            if st.button("Sign document", key=f"btnsign_{ridx}") and sig_name:
                img = add_signature_image(sig_name)
                save_signature(did, current_user[0], "typed", img)
                st.success("Signed and saved.")

def page_start_request(current_user):
    st.subheader("Start a Request")
    
    process = st.selectbox("Choose process template", list(PROCESS_TEMPLATES.keys()))
    with st.expander("Document Details"):
        title = st.text_input("Title *", value=f"{process} - {uuid.uuid4().hex[:6]}")
        default_dept = "Engineering" if process == "Engineering Drawing" else DEPARTMENTS[0]
        default_type = "Drawing" if process == "Engineering Drawing" else DOCUMENT_TYPES[0]
        department = st.selectbox("Department *", DEPARTMENTS, index=DEPARTMENTS.index(default_dept))
        doc_type = st.selectbox("Document Type *", DOCUMENT_TYPES, index=DOCUMENT_TYPES.index(default_type))
        sensitivity = st.selectbox("Sensitivity", SENSITIVITY, index=1)
        tags = st.text_input("Tags", value=process.lower().replace(" ", ","))
        retention_policy = st.selectbox("Retention Policy", list(RETENTION_POLICIES.keys()), index=3)
        retention_years = 0
        if retention_policy == "Custom":
            retention_years = st.number_input("Custom retention (years)", 1, 50, 5)
        file = st.file_uploader("Upload source file *")
        notes = st.text_area("Notes for approvers")

    priority = st.selectbox("Priority", ["Low", "Normal", "High"], index=1)
    sla_hours = st.number_input("SLA (hours)", 4, 240, 48)

    if st.button("Submit Request"):
        if not (title and file):
            st.error("Please add a title and upload a file.")
            return
        doc_id = create_document_record(title, department, doc_type, sensitivity,
                                        [t.strip() for t in tags.split(",") if t.strip()],
                                        retention_policy, int(retention_years or 0),
                                        current_user[0], status="Review", description=notes)
        v = next_version(doc_id)
        path = save_upload(file, doc_id, v)
        add_version(doc_id, v, path, current_user[0], f"Request init: {notes[:200]}")
        
        assignees = []
        for step_name in PROCESS_TEMPLATES[process]:
            u = get_user_by_name(step_name)
            if u: assignees.append(u[0])
        first_assignee = assignees[0] if assignees else ""
        tid = create_ticket(current_user[0], process, doc_id, notes, priority, int(sla_hours), first_assignee)
        for idx, uid in enumerate(assignees):
            assign_approval(doc_id, uid, status="pending" if idx == 0 else "queued")
        st.success(f"Request created. Ticket: {tid[:8]}… Document: {doc_id[:8]}…")

def page_my_tasks(current_user):
    st.subheader("My Tasks")

    st.markdown("### Tickets")
    tickets = list_my_tickets(current_user[0])
    if not tickets:
        st.caption("No tickets.")
    for tid, ptype, status, prio, sla, notes, doc_id, created_at in tickets:
        with st.expander(f"{ptype} — {status} — {tid[:8]}…"):
            st.caption(f"Priority: {prio} • SLA: {sla}h • Created: {created_at}")
            st.write(notes or "No notes")
            c1, c2 = st.columns(2)
            if c1.button("Close Ticket", key=f"close_{tid}"):
                close_ticket(tid, current_user[0])
                st.success("Ticket closed.")
            c2.code(f"Linked Document: {doc_id}")

    st.markdown("---")
    st.markdown("### Approvals")
    page_my_approvals_enhanced(current_user)

def page_admin(current_user):
    st.subheader("Admin")
    if st.button("Re-seed demo users"):
        seed_users()
        st.success("Users seeded.")
    
    st.markdown("### Audit trail (last 50)")
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT at, actor, entity, action, entity_id, details FROM audit ORDER BY at DESC LIMIT 50")
    rows = cur.fetchall()
    conn.close()
    st.dataframe(rows, hide_index=True, use_container_width=True)

# ============================================================
# Main App
# ============================================================
@st.cache_resource
def _bootstrap():
    init_db()
    seed_users()
    return True

def main():
    _bootstrap()
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)

    users = get_users()
    name_to_tuple = {u[1]: u for u in users}
    st.sidebar.header("Who are you?")
    choice = st.sidebar.selectbox("User", list(name_to_tuple.keys()))
    current_user = name_to_tuple[choice]
    st.sidebar.info(f"Role: {current_user[2]}")

    # Show pending approvals count
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM approvals WHERE assigned_to=? AND status='pending'", (current_user[0],))
    pending_count = cur.fetchone()[0]
    conn.close()
    
    if pending_count > 0:
        st.sidebar.error(f"🔔 {pending_count} pending approval(s)")

    page = st.sidebar.radio("Go to", [
        "📄 Create Document", 
        "⚡ My Approvals", 
        "🔍 Search & Browse", 
        "📁 Upload", 
        "🎫 Start Request",
        "✅ My Tasks", 
        "⚙️ Admin"
    ])
    
    if page == "📄 Create Document":
        page_create_document_enhanced(current_user)
    elif page == "⚡ My Approvals":
        page_my_approvals_enhanced(current_user)
    elif page == "🔍 Search & Browse":
        page_browse(current_user)
    elif page == "📁 Upload":
        page_upload(current_user)
    elif page == "🎫 Start Request":
        page_start_request(current_user)
    elif page == "✅ My Tasks":
        page_my_tasks(current_user)
    else:
        page_admin(current_user)

if __name__ == "__main__":
    main()
