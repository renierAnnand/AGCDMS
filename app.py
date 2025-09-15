import os, uuid, sqlite3, datetime as dt
from typing import List, Tuple, Optional, Dict
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
# Enhanced Domain configuration
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

# Enhanced approval workflows with different paths
APPROVAL_WORKFLOWS = {
    "Simple Approval": {
        "steps": [{"role": "Department Manager", "required": True}],
        "description": "Single manager approval",
        "max_parallel": 1
    },
    "Standard Review": {
        "steps": [
            {"role": "Department Lead", "required": True},
            {"role": "Department Manager", "required": True}
        ],
        "description": "Two-step departmental review",
        "max_parallel": 1
    },
    "Legal & Finance": {
        "steps": [
            {"role": "Legal Counsel", "required": True},
            {"role": "Finance Manager", "required": True},
            {"role": "Department Manager", "required": False}
        ],
        "description": "Parallel legal and finance review",
        "max_parallel": 2
    },
    "Engineering Drawing": {
        "steps": [
            {"role": "Engineering Lead", "required": True},
            {"role": "QA Reviewer", "required": True},
            {"role": "Engineering Manager", "required": True}
        ],
        "description": "Technical review workflow",
        "max_parallel": 1
    },
    "Executive Approval": {
        "steps": [
            {"role": "Department Manager", "required": True},
            {"role": "Director", "required": True},
            {"role": "VP", "required": True}
        ],
        "description": "High-level executive approval",
        "max_parallel": 1
    }
}

# Process templates for work management
PROCESS_TEMPLATES = {
    "Engineering Drawing": ["Engineering Lead", "QA Reviewer", "Engineering Manager"],
    "Policy Update": ["Department Owner", "HR Approver"],
    "Supplier Contract": ["Procurement Lead", "Legal Counsel", "Procurement Manager"],
    "Financial Document": ["Finance Lead", "Finance Manager", "Director"],
}

# Enhanced user roles and demo users
ROLES_HIERARCHY = {
    "Admin": 10,
    "VP": 9,
    "Director": 8,
    "Department Manager": 7,
    "Engineering Manager": 6,
    "Finance Manager": 6,
    "Legal Counsel": 6,
    "Department Lead": 5,
    "Engineering Lead": 5,
    "Finance Lead": 5,
    "Procurement Lead": 5,
    "Department Owner": 5,
    "QA Reviewer": 4,
    "HR Approver": 4,
    "Procurement Manager": 4,
    "Approver": 3,
    "Contributor": 2,
    "Viewer": 1
}

SEED_USERS = [
    ("u-admin", "Admin User", "admin@example.com", "Admin"),
    ("u-vp", "Victoria VP", "vp@example.com", "VP"),
    ("u-director", "David Director", "director@example.com", "Director"),
    ("u-deptmgr", "Diana Manager", "deptmgr@example.com", "Department Manager"),
    ("u-engmgr", "Engineering Manager", "engmgr@example.com", "Engineering Manager"),
    ("u-finmgr", "Finance Manager", "finmgr@example.com", "Finance Manager"),
    ("u-legal", "Legal Counsel", "legal@example.com", "Legal Counsel"),
    ("u-englead", "Engineering Lead", "englead@example.com", "Engineering Lead"),
    ("u-finlead", "Finance Lead", "finlead@example.com", "Finance Lead"),
    ("u-proclead", "Procurement Lead", "proclead@example.com", "Procurement Lead"),
    ("u-deptowner", "Department Owner", "owner@example.com", "Department Owner"),
    ("u-qarev", "QA Reviewer", "qarev@example.com", "QA Reviewer"),
    ("u-hrappr", "HR Approver", "hrappr@example.com", "HR Approver"),
    ("u-procmgr", "Procurement Manager", "procmgr@example.com", "Procurement Manager"),
    ("u-approver", "Aisha Approver", "aisha@example.com", "Approver"),
    ("u-contrib", "Omar Contributor", "omar@example.com", "Contributor"),
    ("u-view", "Vera Viewer", "vera@example.com", "Viewer"),
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
# Enhanced DB Setup
# ============================================================
def connect():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = connect()
    cur = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT,
        role TEXT NOT NULL,
        department TEXT DEFAULT '',
        active INTEGER DEFAULT 1
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        department TEXT,
        doc_type TEXT,
        sensitivity TEXT,
        tags TEXT,
        retention_policy TEXT,
        retention_years INTEGER,
        status TEXT,               -- Draft/Review/Approved/Executed/Rejected
        workflow_type TEXT,        -- Which approval workflow to use
        effective_date TEXT,
        expiry_date TEXT,
        created_at TEXT,
        created_by TEXT,
        last_modified_at TEXT,
        last_modified_by TEXT,
        active INTEGER DEFAULT 1
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS versions (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        file_name TEXT NOT NULL,
        file_size INTEGER DEFAULT 0,
        note TEXT,
        created_at TEXT,
        created_by TEXT
    )""")

    # Enhanced approvals table with workflow steps
    cur.execute("""CREATE TABLE IF NOT EXISTS approvals (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        workflow_step INTEGER NOT NULL,
        assigned_to TEXT NOT NULL,
        status TEXT NOT NULL,      -- queued | pending | approved | rejected | skipped
        comment TEXT,
        required BOOLEAN DEFAULT 1,
        created_at TEXT,
        decided_at TEXT,
        due_date TEXT
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

    # Enhanced audit table
    cur.execute("""CREATE TABLE IF NOT EXISTS audit (
        id TEXT PRIMARY KEY,
        entity TEXT,
        entity_id TEXT,
        action TEXT,
        actor TEXT,
        at TEXT,
        details TEXT,
        ip_address TEXT DEFAULT '',
        user_agent TEXT DEFAULT ''
    )""")

    # Comments/discussions on documents
    cur.execute("""CREATE TABLE IF NOT EXISTS comments (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        parent_comment_id TEXT,
        author TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT,
        edited_at TEXT
    )""")

    conn.commit()
    conn.close()

def seed_users():
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    if (cur.fetchone() or [0])[0] == 0:
        # Add department info to some users
        enhanced_users = []
        for user_id, name, email, role in SEED_USERS:
            dept = ""
            if "Engineering" in role or "Engineering" in name:
                dept = "Engineering"
            elif "Finance" in role or "Finance" in name:
                dept = "Finance"
            elif "Legal" in role:
                dept = "Legal"
            elif "HR" in role:
                dept = "HR"
            elif "Procurement" in role or "Procurement" in name:
                dept = "Procurement"
            enhanced_users.append((user_id, name, email, role, dept))
        
        cur.executemany("INSERT INTO users (id,name,email,role,department) VALUES (?,?,?,?,?)", enhanced_users)
        conn.commit()
    conn.close()

def add_audit(entity: str, entity_id: str, action: str, actor: str, details: str = "", ip: str = "", ua: str = ""):
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO audit (id, entity, entity_id, action, actor, at, details, ip_address, user_agent) VALUES (?,?,?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), entity, entity_id, action, actor, now_iso(), details, ip, ua)
    )
    conn.commit()
    conn.close()

# ============================================================
# Enhanced Helper Functions
# ============================================================
def get_users() -> List[Tuple[str, str, str, str]]:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, name, role, department FROM users WHERE active=1 ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_user_by_name(name: str) -> Optional[Tuple[str, str, str, str]]:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, name, role, department FROM users WHERE name=? AND active=1", (name,))
    row = cur.fetchone()
    conn.close()
    return row

def get_users_by_role(role: str) -> List[Tuple[str, str, str, str]]:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, name, role, department FROM users WHERE role=? AND active=1", (role,))
    rows = cur.fetchall()
    conn.close()
    return rows

def can_user_approve(user_role: str, required_role: str) -> bool:
    """Check if user has sufficient authority to approve"""
    user_level = ROLES_HIERARCHY.get(user_role, 0)
    required_level = ROLES_HIERARCHY.get(required_role, 0)
    return user_level >= required_level

# ============================================================
# Enhanced Document Operations
# ============================================================
def create_document_record(title: str, description: str, department: str, doc_type: str, 
                          sensitivity: str, tags: List[str], retention_policy: str, 
                          retention_years: int, workflow_type: str, created_by: str, 
                          status: str = "Draft", effective_date: Optional[str] = None, 
                          expiry_date: Optional[str] = None) -> str:
    doc_id = str(uuid.uuid4())
    now = now_iso()
    conn = connect()
    cur = conn.cursor()
    cur.execute("""INSERT INTO documents
        (id, title, description, department, doc_type, sensitivity, tags, retention_policy, retention_years,
         status, workflow_type, effective_date, expiry_date, created_at, created_by, last_modified_at, last_modified_by, active)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
        (doc_id, title, description, department, doc_type, sensitivity, ",".join(tags),
         retention_policy, int(retention_years or 0), status, workflow_type,
         effective_date or "", expiry_date or "", now, created_by, now, created_by))
    conn.commit()
    conn.close()
    add_audit("document", doc_id, "create", created_by, f"Title: {title}, Type: {doc_type}")
    return doc_id

def get_document(doc_id: str) -> Optional[dict]:
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT id, title, description, department, doc_type, sensitivity, tags, 
                          retention_policy, retention_years, status, workflow_type, 
                          effective_date, expiry_date, created_at, created_by, 
                          last_modified_at, last_modified_by
                   FROM documents WHERE id=? AND active=1""", (doc_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    
    return {
        "id": row[0], "title": row[1], "description": row[2], "department": row[3],
        "doc_type": row[4], "sensitivity": row[5], "tags": row[6], "retention_policy": row[7],
        "retention_years": row[8], "status": row[9], "workflow_type": row[10],
        "effective_date": row[11], "expiry_date": row[12], "created_at": row[13],
        "created_by": row[14], "last_modified_at": row[15], "last_modified_by": row[16]
    }

def update_document_status(doc_id: str, status: str, user_id: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE documents SET status=?, last_modified_at=?, last_modified_by=? WHERE id=?",
                (status, now_iso(), user_id, doc_id))
    conn.commit()
    conn.close()
    add_audit("document", doc_id, "status_change", user_id, f"Status changed to: {status}")

def next_version(document_id: str) -> int:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT MAX(version) FROM versions WHERE document_id=?", (document_id,))
    v = cur.fetchone()[0]
    conn.close()
    return (v or 0) + 1

def save_upload(file, doc_id: str, version: int) -> Tuple[str, str, int]:
    name = f"{doc_id}_v{version}_{file.name}"
    path = os.path.join(FILES_DIR, name)
    with open(path, "wb") as f:
        content = file.getbuffer()
        f.write(content)
        size = len(content)
    return path, file.name, size

def add_version(document_id: str, version: int, file_path: str, file_name: str, file_size: int, created_by: str, note: str = ""):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""INSERT INTO versions
        (id, document_id, version, file_path, file_name, file_size, note, created_at, created_by)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), document_id, version, file_path, file_name, file_size, note, now_iso(), created_by))
    conn.commit()
    conn.close()
    add_audit("version", document_id, f"v{version}", created_by, f"File: {file_name}, Note: {note}")

# ============================================================
# Enhanced Approval Workflow System
# ============================================================
def create_approval_workflow(document_id: str, workflow_type: str, created_by: str):
    """Create approval workflow steps for a document"""
    if workflow_type not in APPROVAL_WORKFLOWS:
        return False
    
    workflow = APPROVAL_WORKFLOWS[workflow_type]
    conn = connect()
    cur = conn.cursor()
    
    # Clear any existing approvals for this document
    cur.execute("DELETE FROM approvals WHERE document_id=?", (document_id,))
    
    # Create approval steps
    step_num = 1
    pending_assigned = 0
    max_parallel = workflow.get("max_parallel", 1)
    
    for step in workflow["steps"]:
        required_role = step["role"]
        is_required = step["required"]
        
        # Find users with this role or higher authority
        users = get_users_by_role(required_role)
        if not users:
            # Fallback: find users with sufficient authority
            all_users = get_users()
            users = [u for u in all_users if can_user_approve(u[2], required_role)]
        
        if users:
            # Assign to first available user (in real system, might use round-robin or workload balancing)
            assigned_user = users[0][0]  # user_id
            
            # Determine initial status
            if pending_assigned < max_parallel:
                initial_status = "pending"
                pending_assigned += 1
            else:
                initial_status = "queued"
            
            # Calculate due date (48 hours from now for pending, later for queued)
            due_date = (dt.datetime.utcnow() + dt.timedelta(hours=48 if initial_status == "pending" else 72)).isoformat()
            
            cur.execute("""INSERT INTO approvals
                (id, document_id, workflow_step, assigned_to, status, comment, required, created_at, decided_at, due_date)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), document_id, step_num, assigned_user, initial_status, 
                 "", is_required, now_iso(), "", due_date))
        
        step_num += 1
    
    conn.commit()
    conn.close()
    add_audit("workflow", document_id, "create", created_by, f"Workflow: {workflow_type}")
    return True

def get_document_approvals(document_id: str) -> List[dict]:
    """Get all approval steps for a document with user details"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT a.id, a.workflow_step, a.assigned_to, a.status, a.comment, 
                          a.required, a.created_at, a.decided_at, a.due_date,
                          u.name, u.role
                   FROM approvals a 
                   JOIN users u ON a.assigned_to = u.id
                   WHERE a.document_id=? 
                   ORDER BY a.workflow_step, a.created_at""", (document_id,))
    rows = cur.fetchall()
    conn.close()
    
    approvals = []
    for row in rows:
        approvals.append({
            "id": row[0], "step": row[1], "assigned_to": row[2], "status": row[3],
            "comment": row[4], "required": bool(row[5]), "created_at": row[6],
            "decided_at": row[7], "due_date": row[8], "user_name": row[9], "user_role": row[10]
        })
    return approvals

def process_approval_decision(document_id: str, approver_id: str, decision: str, comment: str):
    """Process an approval decision and update workflow state"""
    conn = connect()
    cur = conn.cursor()
    
    # Update the approval decision
    cur.execute("""UPDATE approvals
       SET status=?, comment=?, decided_at=?
       WHERE document_id=? AND assigned_to=? AND status='pending'""",
       (decision, comment, now_iso(), document_id, approver_id))
    
    # Check if we need to advance the workflow
    if decision == "approved":
        # Promote next queued approver(s) to pending
        cur.execute("""SELECT id FROM approvals 
                       WHERE document_id=? AND status='queued' 
                       ORDER BY workflow_step, created_at 
                       LIMIT 2""", (document_id,))  # Allow up to 2 parallel
        next_approvers = cur.fetchall()
        
        for (next_id,) in next_approvers:
            cur.execute("UPDATE approvals SET status='pending' WHERE id=?", (next_id,))
        
        # Check if workflow is complete
        cur.execute("""SELECT COUNT(*) FROM approvals 
                       WHERE document_id=? AND required=1 AND status NOT IN ('approved', 'skipped')""", 
                    (document_id,))
        remaining_required = cur.fetchone()[0]
        
        if remaining_required == 0:
            # All required approvals complete - update document status
            cur.execute("UPDATE documents SET status='Approved', last_modified_at=? WHERE id=?",
                       (now_iso(), document_id))
            add_audit("document", document_id, "workflow_complete", approver_id, "All required approvals obtained")
    
    elif decision == "rejected":
        # Rejection - update document status and cancel remaining approvals
        cur.execute("UPDATE documents SET status='Rejected', last_modified_at=? WHERE id=?",
                   (now_iso(), document_id))
        cur.execute("UPDATE approvals SET status='skipped' WHERE document_id=? AND status IN ('pending', 'queued')",
                   (document_id,))
        add_audit("document", document_id, "workflow_rejected", approver_id, f"Rejected: {comment}")
    
    conn.commit()
    conn.close()
    add_audit("approval", document_id, decision, approver_id, comment)

# ============================================================
# Enhanced UI Pages
# ============================================================
def page_create_document(current_user):
    st.subheader("📄 Create New Document")
    
    with st.form("create_document_form"):
        # Basic Information
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
        
        description = st.text_area("Description", height=100, 
                                  help="Brief description of the document's purpose and content")
        tags = st.text_input("Tags (comma-separated)", 
                            placeholder="policy, procedure, contract, etc.",
                            help="Keywords to help with searching and categorization")
        
        # Workflow Selection
        st.markdown("### Approval Workflow")
        workflow_type = st.selectbox("Choose Approval Workflow *", 
                                   list(APPROVAL_WORKFLOWS.keys()),
                                   help="Select the appropriate approval process")
        
        if workflow_type:
            workflow = APPROVAL_WORKFLOWS[workflow_type]
            st.info(f"**{workflow['description']}**")
            st.write("Approval steps:")
            for i, step in enumerate(workflow['steps'], 1):
                required_text = "Required" if step['required'] else "Optional"
                st.write(f"  {i}. {step['role']} ({required_text})")
        
        # File Upload
        st.markdown("### File Upload")
        uploaded_file = st.file_uploader("Select document file *", 
                                       help="Upload the document file (PDF, DOCX, etc.)")
        version_note = st.text_area("Version Notes", height=80,
                                  placeholder="Initial version, key changes, etc.")
        
        # Effective Date
        st.markdown("### Dates")
        col1, col2 = st.columns(2)
        with col1:
            effective_date = st.date_input("Effective Date", help="When this document becomes active")
        with col2:
            # Auto-calculate expiry based on retention policy
            expiry_date = st.date_input("Expiry Date", help="When this document expires (optional)")
        
        # Submit
        submitted = st.form_submit_button("Create Document & Start Approval", type="primary")
    
    if submitted:
        if not title or not uploaded_file or not workflow_type:
            st.error("Please fill in all required fields (marked with *)")
            return
        
        # Create document record
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        doc_id = create_document_record(
            title=title,
            description=description,
            department=department,
            doc_type=doc_type,
            sensitivity=sensitivity,
            tags=tag_list,
            retention_policy=retention_policy,
            retention_years=int(retention_years or 0),
            workflow_type=workflow_type,
            created_by=current_user[0],
            status="Review",  # Start in review status
            effective_date=effective_date.isoformat() if effective_date else None,
            expiry_date=expiry_date.isoformat() if expiry_date else None
        )
        
        # Add initial version
        version = next_version(doc_id)
        file_path, file_name, file_size = save_upload(uploaded_file, doc_id, version)
        add_version(doc_id, version, file_path, file_name, file_size, current_user[0], version_note)
        
        # Create approval workflow
        if create_approval_workflow(doc_id, workflow_type, current_user[0]):
            st.success(f"✅ Document created successfully!")
            st.info(f"📋 Document ID: `{doc_id}`")
            st.info(f"🔄 Approval workflow '{workflow_type}' has been initiated")
            
            # Show initial approvers
            approvals = get_document_approvals(doc_id)
            pending_approvals = [a for a in approvals if a["status"] == "pending"]
            if pending_approvals:
                st.write("**Initial Approvers Assigned:**")
                for approval in pending_approvals:
                    st.write(f"• {approval['user_name']} ({approval['user_role']})")
        else:
            st.error("Failed to create approval workflow. Please contact administrator.")

def page_my_approvals_enhanced(current_user):
    st.subheader("⚡ My Pending Approvals")
    
    conn = connect()
    cur = conn.cursor()
    
    # Get pending approvals with document details
    cur.execute("""SELECT a.document_id, d.title, d.doc_type, d.department, d.sensitivity,
                          a.status, a.comment, a.created_at, a.due_date, a.required,
                          d.created_by, u.name as creator_name
                   FROM approvals a 
                   JOIN documents d ON a.document_id = d.id
                   JOIN users u ON d.created_by = u.id
                   WHERE a.assigned_to=? AND a.status='pending'
                   ORDER BY a.due_date ASC, a.created_at ASC""", (current_user[0],))
    pending = cur.fetchall()
    
    # Get completed approvals for reference
    cur.execute("""SELECT a.document_id, d.title, a.status, a.decided_at, a.comment
                   FROM approvals a 
                   JOIN documents d ON a.document_id = d.id
                   WHERE a.assigned_to=? AND a.status IN ('approved', 'rejected')
                   ORDER BY a.decided_at DESC LIMIT 10""", (current_user[0],))
    completed = cur.fetchall()
    conn.close()
    
    if not pending:
        st.success("🎉 No pending approvals! You're all caught up.")
    else:
        st.write(f"You have **{len(pending)}** documents awaiting your approval:")
        
        for i, (doc_id, title, doc_type, dept, sens, status, comment, created_at, due_date, required, creator_id, creator_name) in enumerate(pending):
            # Calculate urgency
            due_dt = dt.datetime.fromisoformat(due_date)
            now_dt = dt.datetime.utcnow()
            hours_remaining = (due_dt - now_dt).total_seconds() / 3600
            
            # Color code by urgency
            if hours_remaining < 0:
                urgency_color = "🔴"
                urgency_text = f"OVERDUE by {abs(hours_remaining):.1f}h"
            elif hours_remaining < 4:
                urgency_color = "🟠"
                urgency_text = f"{hours_remaining:.1f}h remaining"
            elif hours_remaining < 24:
                urgency_color = "🟡"
                urgency_text = f"{hours_remaining:.1f}h remaining"
            else:
                urgency_color = "🟢"
                urgency_text = f"{hours_remaining/24:.1f} days remaining"
            
            with st.expander(f"{urgency_color} {title} — {doc_type} · {dept}", expanded=hours_remaining < 4):
                # Document details
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.write(f"**Creator:** {creator_name}")
                    st.write(f"**Sensitivity:** {sens}")
                    st.write(f"**Required:** {'Yes' if required else 'No'}")
                with col2:
                    st.write(f"**Due:** {urgency_text}")
                    st.write(f"**Created:** {created_at[:10]}")
                with col3:
                    # Quick document preview link
                    if st.button("📋 View Document", key=f"view_{i}"):
                        st.session_state.selected_doc_id = doc_id
                
                # Get document versions for download
                versions = list_versions(doc_id)
                if versions:
                    latest_version = versions[0]  # Most recent
                    version_num, file_path, _, _, _ = latest_version
                    if os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            st.download_button(
                                f"📥 Download v{version_num}",
                                data=f.read(),
                                file_name=os.path.basename(file_path),
                                key=f"download_{i}"
                            )
                
                # Show workflow progress
                approvals = get_document_approvals(doc_id)
                st.write("**Approval Progress:**")
                progress_cols = st.columns(len(approvals))
                for j, approval in enumerate(approvals):
                    with progress_cols[j]:
                        if approval["status"] == "approved":
                            st.success(f"✅ {approval['user_name']}")
                        elif approval["status"] == "rejected":
                            st.error(f"❌ {approval['user_name']}")
                        elif approval["status"] == "pending":
                            st.warning(f"⏳ {approval['user_name']}")
                        else:
                            st.info(f"⏸️ {approval['user_name']}")
                
                # Approval decision form
                st.markdown("---")
                decision_col1, decision_col2 = st.columns([2, 1])
                with decision_col1:
                    decision_comment = st.text_area(
                        "Comments (optional)", 
                        key=f"comment_{i}",
                        height=80,
                        placeholder="Add your comments, suggestions, or reasons for decision..."
                    )
                
                with decision_col2:
                    st.write("**Make Decision:**")
                    if st.button("✅ Approve", key=f"approve_{i}", type="primary"):
                        process_approval_decision(doc_id, current_user[0], "approved", decision_comment)
                        st.success("Document approved!")
                        st.rerun()
                    
                    if st.button("❌ Reject", key=f"reject_{i}"):
                        if decision_comment.strip():
                            process_approval_decision(doc_id, current_user[0], "rejected", decision_comment)
                            st.error("Document rejected.")
                            st.rerun()
                        else:
                            st.error("Please provide a reason for rejection.")
    
    # Show recent completed approvals
    if completed:
        st.markdown("---")
        st.subheader("📋 Recent Decisions")
        for doc_id, title, status, decided_at, comment in completed:
            status_icon = "✅" if status == "approved" else "❌"
            with st.expander(f"{status_icon} {title} — {status.title()}", expanded=False):
                st.write(f"**Decided:** {decided_at}")
                if comment:
                    st.write(f"**Comment:** {comment}")

def page_document_viewer(current_user):
    """Enhanced document viewing with workflow status"""
    st.subheader("📋 Document Details")
    
    # Get document ID from session state or URL parameter
    doc_id = st.session_state.get("selected_doc_id")
    if not doc_id:
        doc_id = st.text_input("Enter Document ID", placeholder="Document ID...")
        if not doc_id:
            st.info("Enter a document ID to view details.")
            return
    
    # Get document details
    doc = get_document(doc_id)
    if not doc:
        st.error("Document not found.")
        return
    
    # Document header
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.title(doc["title"])
        st.write(doc["description"])
    with col2:
        st.metric("Status", doc["status"])
        st.write(f"**Type:** {doc['doc_type']}")
    with col3:
        st.write(f"**Department:** {doc['department']}")
        st.write(f"**Sensitivity:** {doc['sensitivity']}")
    
    # Workflow progress visualization
    st.markdown("### 🔄 Approval Workflow Progress")
    approvals = get_document_approvals(doc_id)
    
    if approvals:
        # Create progress bar
        total_steps = len(approvals)
        completed_steps = len([a for a in approvals if a["status"] in ["approved", "rejected"]])
        progress = completed_steps / total_steps if total_steps > 0 else 0
        
        st.progress(progress)
        st.write(f"Progress: {completed_steps}/{total_steps} steps completed")
        
        # Detailed workflow steps
        for i, approval in enumerate(approvals, 1):
            col1, col2, col3, col4 = st.columns([1, 2, 2, 3])
            
            with col1:
                if approval["status"] == "approved":
                    st.success(f"Step {i}")
                elif approval["status"] == "rejected":
                    st.error(f"Step {i}")
                elif approval["status"] == "pending":
                    st.warning(f"Step {i}")
                else:
                    st.info(f"Step {i}")
            
            with col2:
                st.write(f"**{approval['user_name']}**")
                st.caption(approval['user_role'])
            
            with col3:
                st.write(f"**Status:** {approval['status'].title()}")
                if approval["decided_at"]:
                    st.caption(f"Decided: {approval['decided_at'][:16]}")
                elif approval["status"] == "pending":
                    due_dt = dt.datetime.fromisoformat(approval['due_date'])
                    st.caption(f"Due: {due_dt.strftime('%Y-%m-%d %H:%M')}")
            
            with col4:
                if approval["comment"]:
                    st.write(f"💬 {approval['comment']}")
    
    # Document versions
    st.markdown("### 📁 Document Versions")
    versions = list_versions(doc_id)
    
    if versions:
        for version_num, file_path, created_at, created_by, note in versions:
            with st.expander(f"Version {version_num} — {created_at[:16]} by {created_by}"):
                if note:
                    st.write(f"**Notes:** {note}")
                
                if os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    st.write(f"**File:** {os.path.basename(file_path)} ({file_size:,} bytes)")
                    
                    with open(file_path, "rb") as f:
                        st.download_button(
                            "📥 Download",
                            data=f.read(),
                            file_name=os.path.basename(file_path),
                            key=f"dl_v{version_num}"
                        )
                else:
                    st.error("File not found on disk")
    
    # Comments section
    st.markdown("### 💬 Comments & Discussion")
    add_comment_to_document(doc_id, current_user)
    display_document_comments(doc_id)

def add_comment_to_document(doc_id: str, current_user):
    """Add comment functionality to documents"""
    with st.form(f"comment_form_{doc_id}"):
        comment_text = st.text_area("Add a comment", height=100, 
                                   placeholder="Share your thoughts, questions, or feedback...")
        submitted = st.form_submit_button("💬 Post Comment")
        
        if submitted and comment_text.strip():
            conn = connect()
            cur = conn.cursor()
            cur.execute("""INSERT INTO comments 
                (id, document_id, parent_comment_id, author, content, created_at, edited_at)
                VALUES (?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), doc_id, None, current_user[0], comment_text.strip(), now_iso(), ""))
            conn.commit()
            conn.close()
            add_audit("comment", doc_id, "add", current_user[0], comment_text[:100])
            st.success("Comment added!")
            st.rerun()

def display_document_comments(doc_id: str):
    """Display comments for a document"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT c.id, c.content, c.created_at, c.edited_at, u.name
                   FROM comments c 
                   JOIN users u ON c.author = u.id
                   WHERE c.document_id=? AND c.parent_comment_id IS NULL
                   ORDER BY c.created_at DESC""", (doc_id,))
    comments = cur.fetchall()
    conn.close()
    
    if comments:
        for comment_id, content, created_at, edited_at, author_name in comments:
            with st.container():
                st.markdown(f"**{author_name}** — *{created_at[:16]}*")
                st.write(content)
                if edited_at:
                    st.caption(f"Edited: {edited_at[:16]}")
                st.markdown("---")
    else:
        st.info("No comments yet. Be the first to comment!")

def page_enhanced_browse(current_user):
    """Enhanced document browsing with better filtering and workflow status"""
    st.subheader("🔍 Browse Documents")
    
    # Enhanced search and filters
    with st.form("enhanced_search_form"):
        col1, col2 = st.columns([3, 1])
        with col1:
            search_query = st.text_input("🔍 Search documents", 
                                       placeholder="Search by title, description, tags...")
        with col2:
            search_submitted = st.form_submit_button("Search", type="primary")
        
        # Filter row
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
        with filter_col1:
            dept_filter = st.selectbox("Department", ["All"] + DEPARTMENTS)
        with filter_col2:
            type_filter = st.selectbox("Document Type", ["All"] + DOCUMENT_TYPES)
        with filter_col3:
            status_filter = st.selectbox("Status", ["All", "Draft", "Review", "Approved", "Rejected", "Executed"])
        with filter_col4:
            sensitivity_filter = st.selectbox("Sensitivity", ["All"] + SENSITIVITY)
    
    # Build filter dictionary
    filters = {
        "q": search_query if search_query else None,
        "department": dept_filter if dept_filter != "All" else None,
        "doc_type": type_filter if type_filter != "All" else None,
        "status": status_filter if status_filter != "All" else None,
        "sensitivity": sensitivity_filter if sensitivity_filter != "All" else None
    }
    
    # Get documents
    documents = list_documents(filters)
    
    if not documents:
        st.info("No documents found matching your criteria.")
        return
    
    # Display results
    st.write(f"Found **{len(documents)}** documents:")
    
    for i, (doc_id, title, dept, doc_type, sens, tags, status, created_at, created_by) in enumerate(documents):
        # Status indicator
        status_colors = {
            "Draft": "🟡", "Review": "🔵", "Approved": "🟢", 
            "Rejected": "🔴", "Executed": "✅"
        }
        status_icon = status_colors.get(status, "⚫")
        
        with st.expander(f"{status_icon} {title} — {doc_type} · {dept} · {sens}"):
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.write(f"**Created:** {created_at[:10]} by {created_by}")
                if tags:
                    st.write(f"**Tags:** {tags}")
                
                # Quick action buttons
                button_col1, button_col2, button_col3 = st.columns(3)
                with button_col1:
                    if st.button("👁️ View Details", key=f"view_detail_{i}"):
                        st.session_state.selected_doc_id = doc_id
                        st.rerun()
                
                with button_col2:
                    # Download latest version
                    versions = list_versions(doc_id)
                    if versions:
                        latest = versions[0]
                        if os.path.exists(latest[1]):
                            with open(latest[1], "rb") as f:
                                st.download_button(
                                    "📥 Download",
                                    data=f.read(),
                                    file_name=os.path.basename(latest[1]),
                                    key=f"dl_browse_{i}"
                                )
                
                with button_col3:
                    # Show workflow status
                    if status in ["Review", "Approved"]:
                        approvals = get_document_approvals(doc_id)
                        pending_count = len([a for a in approvals if a["status"] == "pending"])
                        if pending_count > 0:
                            st.info(f"⏳ {pending_count} pending")
                        else:
                            st.success("✅ Complete")
            
            with col2:
                st.metric("Status", status)
                st.write(f"**Type:** {doc_type}")
            
            with col3:
                st.write(f"**Department:** {dept}")
                st.write(f"**Sensitivity:** {sens}")

def list_documents(filters: dict):
    """Enhanced document listing with better search"""
    conn = connect()
    cur = conn.cursor()
    query = """SELECT id, title, department, doc_type, sensitivity, tags, status, created_at, created_by 
               FROM documents WHERE active=1"""
    args = []
    
    if filters.get("q"):
        q = f"%{filters['q'].lower()}%"
        query += """ AND (LOWER(title) LIKE ? OR LOWER(description) LIKE ? OR 
                         LOWER(tags) LIKE ? OR LOWER(department) LIKE ? OR LOWER(doc_type) LIKE ?)"""
        args += [q, q, q, q, q]
    
    for field in ["department", "doc_type", "sensitivity", "status"]:
        if filters.get(field):
            query += f" AND {field}=?"
            args.append(filters[field])
    
    query += " ORDER BY created_at DESC"
    cur.execute(query, args)
    rows = cur.fetchall()
    conn.close()
    return rows

def list_versions(document_id: str):
    """Get document versions"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT version, file_path, created_at, created_by, note 
                   FROM versions WHERE document_id=? ORDER BY version DESC""", (document_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

# ============================================================
# Enhanced Main App
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
    
    # User selection
    users = get_users()
    name_to_tuple = {f"{u[1]} ({u[2]})": u for u in users}
    
    st.sidebar.header("👤 User Profile")
    choice = st.sidebar.selectbox("Select User", list(name_to_tuple.keys()))
    current_user = name_to_tuple[choice]
    
    st.sidebar.info(f"**Role:** {current_user[2]}")
    if current_user[3]:  # department
        st.sidebar.info(f"**Department:** {current_user[3]}")
    
    # Navigation
    st.sidebar.header("📋 Navigation")
    
    # Show pending approvals count
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM approvals WHERE assigned_to=? AND status='pending'", (current_user[0],))
    pending_count = cur.fetchone()[0]
    conn.close()
    
    approval_text = f"My Approvals ({pending_count})" if pending_count > 0 else "My Approvals"
    if pending_count > 0:
        st.sidebar.error(f"🔔 {pending_count} pending approval(s)")
    
    # Enhanced navigation menu
    pages = {
        "Create Document": "📄 Create Document",
        "My Approvals": f"⚡ {approval_text}",
        "Browse Documents": "🔍 Browse Documents", 
        "Document Viewer": "📋 Document Viewer",
        "Upload Legacy": "📁 Upload Legacy",
        "Start Request": "🎫 Start Request",
        "My Tasks": "✅ My Tasks",
        "Admin": "⚙️ Admin"
    }
    
    selected_page = st.sidebar.radio("Pages", list(pages.keys()), 
                                   format_func=lambda x: pages[x])
    
    # Route to appropriate page
    if selected_page == "Create Document":
        page_create_document(current_user)
    elif selected_page == "My Approvals":
        page_my_approvals_enhanced(current_user)
    elif selected_page == "Browse Documents":
        page_enhanced_browse(current_user)
    elif selected_page == "Document Viewer":
        page_document_viewer(current_user)
    elif selected_page == "Upload Legacy":
        page_upload(current_user)  # Keep original simple upload
    elif selected_page == "Start Request":
        page_start_request(current_user)  # Keep original workflow
    elif selected_page == "My Tasks":
        page_my_tasks(current_user)  # Keep original
    else:
        page_admin(current_user)  # Keep original

# Original functions to maintain compatibility
def page_upload(current_user):
    st.subheader("📁 Upload Legacy Document")
    st.info("Use this for uploading existing documents without formal approval workflow.")
    
    title = st.text_input("Title *")
    department = st.selectbox("Department *", DEPARTMENTS)
    doc_type = st.selectbox("Document Type *", DOCUMENT_TYPES)
    sensitivity = st.selectbox("Sensitivity", SENSITIVITY, index=1)
    tags = st.text_input("Tags (comma-separated)", placeholder="legacy, imported, etc.")
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
        doc_id = create_document_record(title, "", department, doc_type, sensitivity,
                                        [t.strip() for t in tags.split(",") if t.strip()],
                                        retention_policy, int(retention_years or 0),
                                        "", current_user[0], status="Approved")  # Skip workflow
        v = next_version(doc_id)
        path, fname, fsize = save_upload(file, doc_id, v)
        add_version(doc_id, v, path, fname, fsize, current_user[0], note)
        st.success(f"Uploaded v{v} for '{title}' (bypassed approval workflow).")

def page_start_request(current_user):
    st.subheader("🎫 Start a Request (Manual Ticket)")
    st.info("Use this for formal process requests with predefined approval chains.")
    
    process = st.selectbox("Choose process template", list(PROCESS_TEMPLATES.keys()))
    with st.expander("Attach / Create Document"):
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
        notes = st.text_area("Notes for approvers", placeholder="Key changes, revision, related PO/WO, etc.")

    priority = st.selectbox("Priority", ["Low", "Normal", "High"], index=1)
    sla_hours = st.number_input("SLA (hours)", 4, 240, 48)

    if st.button("Submit Request"):
        if not (title and file):
            st.error("Please add a title and upload a file.")
            return
        doc_id = create_document_record(title, notes, department, doc_type, sensitivity,
                                        [t.strip() for t in tags.split(",") if t.strip()],
                                        retention_policy, int(retention_years or 0),
                                        "Standard Review", current_user[0], status="Review")
        v = next_version(doc_id)
        path, fname, fsize = save_upload(file, doc_id, v)
        add_version(doc_id, v, path, fname, fsize, current_user[0], f"Request init: {notes[:200]}")
        
        # Use legacy approval system for compatibility
        assignees = []
        for step_name in PROCESS_TEMPLATES[process]:
            u = get_user_by_name(step_name)
            if u: assignees.append(u[0])
        first_assignee = assignees[0] if assignees else ""
        tid = create_ticket(current_user[0], process, doc_id, notes, priority, int(sla_hours), first_assignee)
        
        st.success(f"Request created ✔  Ticket: {tid[:8]}…  Document: {doc_id[:8]}…")

def assign_approval(document_id: str, approver_id: str, status: str = "pending"):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""INSERT INTO approvals
        (id, document_id, workflow_step, assigned_to, status, comment, required, created_at, decided_at, due_date)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), document_id, 1, approver_id, status, "", True, now_iso(), "", 
         (dt.datetime.utcnow() + dt.timedelta(hours=48)).isoformat()))
    conn.commit()
    conn.close()
    add_audit("approval", document_id, status, approver_id, "")

def decide_approval(document_id: str, approver_id: str, decision: str, comment: str):
    process_approval_decision(document_id, approver_id, decision, comment)

# Keep other original functions
def page_my_tasks(current_user):
    st.subheader("✅ My Tasks (Tickets & Approvals)")

    st.markdown("### 🎫 Tickets")
    tickets = list_my_tickets(current_user[0])
    if not tickets:
        st.caption("_No tickets._")
    else:
        for tid, ptype, status, prio, sla, notes, doc_id, created_at in tickets:
            with st.expander(f"{ptype} — {status} — {tid[:8]}…"):
                st.caption(f"Priority: {prio} • SLA: {sla}h • Created: {created_at}")
                st.write(notes or "_No notes_")
                c1, c2 = st.columns(2)
                if c1.button("Close Ticket", key=f"close_{tid}"):
                    close_ticket(tid, current_user[0])
                    st.success("Ticket closed.")
                    st.rerun()
                c2.code(f"Linked Document: {doc_id}")

    st.markdown("---")
    st.markdown("### ⚡ Quick Approvals")
    page_my_approvals_enhanced(current_user)

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

def close_ticket(ticket_id: str, user_id: str):
    conn = connect()
    cur = conn.cursor()
    cur.execute("UPDATE tickets SET status='Closed', closed_at=? WHERE id=?", (now_iso(), ticket_id))
    conn.commit()
    conn.close()
    add_audit("ticket", ticket_id, "close", user_id, "")

def page_admin(current_user):
    st.subheader("⚙️ Admin Panel")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 👥 User Management")
        if st.button("Re-seed demo users"):
            seed_users()
            st.success("Users seeded.")
        
        # Show user stats
        users = get_users()
        role_counts = {}
        for user in users:
            role = user[2]
            role_counts[role] = role_counts.get(role, 0) + 1
        
        st.write("**Users by Role:**")
        for role, count in sorted(role_counts.items()):
            st.write(f"• {role}: {count}")
    
    with col2:
        st.markdown("### 📊 System Stats")
        conn = connect()
        cur = conn.cursor()
        
        # Document stats
        cur.execute("SELECT COUNT(*) FROM documents WHERE active=1")
        doc_count = cur.fetchone()[0]
        
        cur.execute("SELECT status, COUNT(*) FROM documents WHERE active=1 GROUP BY status")
        status_counts = dict(cur.fetchall())
        
        cur.execute("SELECT COUNT(*) FROM approvals WHERE status='pending'")
        pending_approvals = cur.fetchone()[0]
        
        conn.close()
        
        st.metric("Total Documents", doc_count)
        st.metric("Pending Approvals", pending_approvals)
        
        st.write("**Documents by Status:**")
        for status, count in status_counts.items():
            st.write(f"• {status}: {count}")
    
    st.markdown("---")
    st.markdown("### 📋 Audit Trail (Last 50)")
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT at, actor, entity, action, entity_id, details 
                   FROM audit ORDER BY at DESC LIMIT 50""")
    rows = cur.fetchall()
    conn.close()
    
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True,
                    column_config={
                        "at": "Timestamp",
                        "actor": "User",
                        "entity": "Entity",
                        "action": "Action", 
                        "entity_id": "ID",
                        "details": "Details"
                    })

if __name__ == "__main__":
    main()
