import os, uuid, sqlite3, datetime as dt
from typing import List, Tuple, Optional
import streamlit as st
from PIL import Image, ImageDraw

# ============================================================
# App configuration - KEEP ORIGINAL
# ============================================================
APP_TITLE = "Enterprise DMS + Work Management Prototype"
DB_PATH = "dms.sqlite3"
FILES_DIR = "dms_files"
os.makedirs(FILES_DIR, exist_ok=True)

# ============================================================
# Domain configuration - ENHANCED BUT COMPATIBLE
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

# NEW: Enhanced approval workflows
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

# Process templates used by Start Request (Work Management)
PROCESS_TEMPLATES = {
    "Engineering Drawing": ["Engineering Lead", "QA Reviewer", "Engineering Manager"],
    "Policy Update": ["Department Owner", "HR Approver"],
    "Supplier Contract": ["Procurement Lead", "Legal Counsel", "Procurement Manager"],
}

# Demo users (Name -> Role=Approver or other). Keep names in sync with PROCESS_TEMPLATES.
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
# Integration stubs (replace with Microsoft Graph / Power Automate later)
# ============================================================
class SharePointStorageStub:
    """Placeholder for SharePoint (Graph API) integration."""
    enabled = False
    def upload(self, local_path: str, *, site_id: str = "", drive_id: str = "", folder_path: str = ""):
        # TODO: replace with real Graph upload
        return {"status": "stubbed", "local_path": local_path, "sharepoint_item_id": None, "url": None}
    def create_metadata_columns(self):
        return {"status": "stubbed"}

class PowerAutomateClientStub:
    """Placeholder for Power Automate HTTP-trigger flows."""
    def __init__(self, flow_url: Optional[str] = None, api_key: Optional[str] = None):
        self.flow_url = flow_url
        self.api_key = api_key
    def send_event(self, event_name: str, payload: dict):
        # TODO: implement POST to your HTTP-triggered Flow
        return {"status": "stubbed", "event": event_name, "payload": payload}

sp_storage = SharePointStorageStub()
pa_client = PowerAutomateClientStub()

# ============================================================
# DB Setup - KEEP EXACTLY THE SAME
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
        status TEXT,               -- Draft/Review/Approved/Executed
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
        status TEXT NOT NULL,      -- queued | pending | approved | rejected
        comment TEXT,
        created_at TEXT,
        decided_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS signatures (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        signer TEXT NOT NULL,
        method TEXT,               -- typed
        image_path TEXT,
        signed_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS tickets (
        id TEXT PRIMARY KEY,
        requester TEXT NOT NULL,
        process_type TEXT NOT NULL,
        linked_document_id TEXT,
        status TEXT,               -- Open | In Progress | Closed
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
# Helpers: Users & Lookups - KEEP ORIGINAL
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
# Document & Version Operations - KEEP ORIGINAL + SMALL ENHANCEMENTS
# ============================================================
def compute_retention_expiry(policy_name: str, created_at: dt.datetime, custom_years: int = 0) -> Optional[dt.datetime]:
    years = RETENTION_POLICIES.get(policy_name, 0)
    if years == -1:
        years = custom_years
    if years <= 0:
        return None
    try:
        return created_at.replace(year=created_at.year + years)
    except ValueError:
        # handle Feb 29
        return (created_at - dt.timedelta(days=1)).replace(year=created_at.year + years)

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
# Enhanced Approvals - Using Original Schema
# ============================================================
def create_sequential_approvals(document_id: str, workflow_type: str, created_by: str):
    """Create sequential approval workflow using original approvals table"""
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
    """Get approval status for a document"""
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
    
    # If approved, promote next queued approver (if any)
    if decision == "approved":
        cur.execute("SELECT id FROM approvals WHERE document_id=? AND status='queued' ORDER BY created_at ASC LIMIT 1", (document_id,))
        nxt = cur.fetchone()
        if nxt:
            cur.execute("UPDATE approvals SET status='pending' WHERE id=?", (nxt[0],))
        else:
            # All approvals complete - update document status
            cur.execute("UPDATE documents SET status='Approved' WHERE id=?", (document_id,))
    elif decision == "rejected":
        # Mark document as rejected and skip remaining approvals
        cur.execute("UPDATE documents SET status='Rejected' WHERE id=?", (document_id,))
        cur.execute("UPDATE approvals SET status='skipped' WHERE document_id=? AND status='queued'", (document_id,))
    
    conn.commit()
    conn.close()
    add_audit("approval", document_id, decision, approver_id, comment)

# ============================================================
# E-Signatures (typed -> PNG artifact)
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
# Tickets (Work Management)
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
# ENHANCED UI PAGES
# ============================================================
def page_create_document_enhanced(current_user):
    st.subheader("📄 Create New Document")
    
    with st.form("create_document_form"):
        # Basic Information
        st.markdown("### 📋 Basic Information")
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
        st.markdown("### 🔄 Approval Workflow")
        workflow_type = st.selectbox("Choose Approval Workflow *", 
                                   list(APPROVAL_WORKFLOWS.keys()),
                                   help="Select the appropriate approval process")
        
        if workflow_type:
            workflow = APPROVAL_WORKFLOWS[workflow_type]
            st.info(f"**{workflow['description']}**")
            st.write("Approval steps:")
            for i, step in enumerate(workflow['steps'], 1):
                st.write(f"  {i}. {step}")
        
        # File Upload
        st.markdown("### 📁 File Upload")
        uploaded_file = st.file_uploader("Select document file *", 
                                       help="Upload the document file (PDF, DOCX, etc.)")
        version_note = st.text_area("Version Notes", height=80,
                                  placeholder="Initial version, key changes, etc.")
        
        # Effective Date
        st.markdown("### 📅 Dates")
        col1, col2 = st.columns(2)
        with col1:
            effective_date = st.date_input("Effective Date", help="When this document becomes active")
        with col2:
            expiry_date = st.date_input("Expiry Date", help="When this document expires (optional)")
        
        # Submit
        submitted = st.form_submit_button("🚀 Create Document & Start Approval", type="primary")
    
    if submitted:
        if not title or not uploaded_file or not workflow_type:
            st.error("Please fill in all required fields (marked with *)")
            return
        
        # Create document record
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
            status="Review",  # Start in review status
            effective_date=effective_date.isoformat() if effective_date else None,
            expiry_date=expiry_date.isoformat() if expiry_date else None,
            description=description,
            workflow_type=workflow_type
        )
        
        # Add initial version
        version = next_version(doc_id)
        file_path = save_upload(uploaded_file, doc_id, version)
        add_version(doc_id, version, file_path, current_user[0], version_note)
        
        # Create approval workflow
        if create_sequential_approvals(doc_id, workflow_type, current_user[0]):
            st.success(f"✅ Document created successfully!")
            st.info(f"📋 Document ID: `{doc_id}`")
            st.info(f"🔄 Approval workflow '{workflow_type}' has been initiated")
            
            # Show initial approvers
            approvals = get_document_approvals(doc_id)
            pending_approvals = [a for a in approvals if a["status"] == "pending"]
            if pending_approvals:
                st.write("**🔔 Initial Approvers Assigned:**")
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
                          a.status, a.comment, a.created_at, d.created_by, u.name as creator_name
                   FROM approvals a 
                   JOIN documents d ON a.document_id = d.id
                   JOIN users u ON d.created_by = u.id
                   WHERE a.assigned_to=? AND a.status='pending'
                   ORDER BY a.created_at ASC""", (current_user[0],))
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
        
        for i, (doc_id, title, doc_type, dept, sens, status, comment, created_at, creator_id, creator_name) in enumerate(pending):
            
            with st.expander(f"📋 {title} — {doc_type} · {dept}", expanded=True):
                # Document details
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.write(f"**Creator:** {creator_name}")
                    st.write(f"**Type:** {doc_type}")
                    st.write(f"**Sensitivity:** {sens}")
                with col2:
                    st.write(f"**Department:** {dept}")
                    st.write(f"**Created:** {created_at[:10]}")
                with col3:
                    # Download latest version
                    versions = list_versions(doc_id)
                    if versions:
                        latest_version = versions[0]
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
                st.write("**🔄 Approval Progress:**")
                
                # Create a simple progress display
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
    
    # Show recent completed approvals
    if completed:
        st.markdown("---")
        st.subheader("📋 Recent Decisions")
        for doc_id, title, status, decided_at, comment in completed[:5]:  # Show only last 5
            status_icon = "✅" if status == "approved" else "❌"
            with st.expander(f"{status_icon} {title} — {status.title()}", expanded=False):
                st.write(f"**Decided:** {decided_at}")
                if comment:
                    st.write(f"**Comment:** {comment}")

# ============================================================
# ORIGINAL UI PAGES - KEEP WORKING
# ============================================================
def page_start_request(current_user):
    st.subheader("🎫 Start a Request (Process Template)")
    
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
        # Create document + version
        doc_id = create_document_record(title, department, doc_type, sensitivity,
                                        [t.strip() for t in tags.split(",") if t.strip()],
                                        retention_policy, int(retention_years or 0),
                                        current_user[0], status="Review", description=notes)
        v = next_version(doc_id)
        path = save_upload(file, doc_id, v)
        add_version(doc_id, v, path, current_user[0], f"Request init: {notes[:200]}")
        # Ticket + initial approvers (first pending, rest queued)
        assignees = []
        for step_name in PROCESS_TEMPLATES[process]:
            u = get_user_by_name(step_name)
            if u: assignees.append(u[0])
        first_assignee = assignees[0] if assignees else ""
        tid = create_ticket(current_user[0], process, doc_id, notes, priority, int(sla_hours), first_assignee)
        for idx, uid in enumerate(assignees):
            assign_approval(doc_id, uid, status="pending" if idx == 0 else "queued")
        st.success(f"Request created ✔  Ticket: {tid[:8]}…  Document: {doc_id[:8]}…  First approver assigned.")

def page_upload(current_user):
    st.subheader("📁 Upload Document")
    title = st.text_input("Title *")
    department = st.selectbox("Department *", DEPARTMENTS)
    doc_type = st.selectbox("Document Type *", DOCUMENT_TYPES)
    sensitivity = st.selectbox("Sensitivity", SENSITIVITY, index=1)
    tags = st.text_input("Tags (comma-separated)", placeholder="policy, HR, onboarding")
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
    st.subheader("🔍 Search & Browse")
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
            st.markdown("**Workflow (ad-hoc assignment)**")
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

def page_my_approvals(current_user):
    st.subheader("My Approvals")
    conn = connect()
    cur = conn.cursor()
    cur.execute("""SELECT a.document_id, d.title, a.status, a.comment, a.created_at
                   FROM approvals a JOIN documents d ON a.document_id=d.id
                   WHERE a.assigned_to=? AND a.status='pending'
                   ORDER BY a.created_at ASC""", (current_user[0],))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        st.info("No pending approvals. 🎉")
    for ridx, (did, title, status, comment, created_at) in enumerate(rows):
        with st.expander(f"{title} — {status}"):
            decision = st.selectbox("Decision", ["approved", "rejected"], key=f"dec_{ridx}")
            comm = st.text_area("Comment", key=f"com_{ridx}")
            if st.button("Submit decision", key=f"btn_{ridx}"):
                decide_approval(did, current_user[0], decision, comm)
                st.success("Decision recorded. (Next approver—if any—has been promoted to pending.)")

def page_my_tasks(current_user):
    st.subheader("✅ My Tasks (Tickets & Approvals)")

    st.markdown("### Tickets")
    tickets = list_my_tickets(current_user[0])
    if not tickets:
        st.caption("_No tickets._")
    for tid, ptype, status, prio, sla, notes, doc_id, created_at in tickets:
        with st.expander(f"{ptype} — {status} — {tid[:8]}…"):
            st.caption(f"Priority: {prio} • SLA: {sla}h • Created: {created_at}")
            st.write(notes or "_No notes_")
            c1, c2 = st.columns(2)
            if c1.button("Close Ticket", key=f"close_{tid}"):
                close_ticket(tid, current_user[0])
                st.success("Ticket closed.")
            c2.code(f"Linked Document: {doc_id}")

    st.markdown("---")
    st.markdown("### Approvals")
    page_my_approvals(current_user)

def page_admin(current_user):
    st.subheader("Admin")
    st.caption("Seed data and view audit trail")
    if st.button("Re-seed demo users"):
        seed_users()
        st.success("Users seeded.")
    st.markdown("### Audit trail (last 200)")
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT at, actor, entity, action, entity_id, details FROM audit ORDER BY at DESC LIMIT 200")
    rows = cur.fetchall()
    conn.close()
    st.dataframe(rows, hide_index=True, use_container_width=True)

# ============================================================
# App entrypoint
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
    st.sidebar.header("Who are you? (role simulation)")
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
