import streamlit as st
import pandas as pd
import numpy as np
import pygsheets
from datetime import datetime, date
import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---------------- load .env (اختياري للإيميل) ----------------
load_dotenv()  # لو عندك ملف .env فيه EMAIL_USER و EMAIL_PASS و ADMIN_EMAIL

EMAIL_USER = os.getenv("EMAIL_USER")      # example: notify.your@gmail.com
EMAIL_PASS = os.getenv("EMAIL_PASS")      # password or app password
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")    # البريد الإداري للتلقي

# ---------------- إعداد Google Sheets ----------------
# لازم يكون عندك ملف JSON للخدمة باسم gspread-creds.json في نفس المجلد
CREDS_FILE = "gspread-creds.json"
GC = None
SHEET_NAME = "StaffApp"  # اسم ملف Google Sheets (يجب أنشاؤه في Drive)

def init_gsheets():
    global GC
    if GC is None:
        try:
            GC = pygsheets.authorize(service_file=CREDS_FILE)
        except Exception as e:
            st.error("فشل الاتصال بـ Google Sheets. تأكد من ملف gspread-creds.json ومشاركته مع الservice account.")
            st.stop()
    try:
        sh = GC.open(SHEET_NAME)
    except Exception as e:
        st.error(f"مشكلة بفتح الملف '{SHEET_NAME}'. تأكد الملف موجود ومشارك مع service account. خطأ: {e}")
        st.stop()
    return sh

# ---------- Helpers لقراءة وكتابة Sheets ----------
def ensure_sheets_exist(sh):
    # ينشئ الأوراق لو مو موجودة
    names = [ws.title for ws in sh.worksheets()]
    if "Employees" not in names:
        sh.add_worksheet("Employees")
        sh.worksheet_by_title("Employees").set_dataframe(pd.DataFrame(columns=[
            "employee_id","name","code","position","residence","contract_start","contract_end",
            "annual_leave","sick_paid","sick_unpaid","sales_perf","exams_perf","commitment",
            "evaluation","behavior","total_perf","points"
        ]), (1,1))
    if "LeaveRequests" not in names:
        sh.add_worksheet("LeaveRequests")
        sh.worksheet_by_title("LeaveRequests").set_dataframe(pd.DataFrame(columns=[
            "id","employee_id","name","type","from","to","proof_url","status","submitted_at"
        ]), (1,1))
    if "Warnings" not in names:
        sh.add_worksheet("Warnings")
        sh.worksheet_by_title("Warnings").set_dataframe(pd.DataFrame(columns=[
            "id","employee_id","name","type","points","date","reason","deducted_salary","status"
        ]), (1,1))
    if "Shifts" not in names:
        sh.add_worksheet("Shifts")
        sh.worksheet_by_title("Shifts").set_dataframe(pd.DataFrame(columns=[
            "id","employee_id","date","shift","start","end","note"
        ]), (1,1))
    if "Notifications" not in names:
        sh.add_worksheet("Notifications")
        sh.worksheet_by_title("Notifications").set_dataframe(pd.DataFrame(columns=[
            "id","employee_id","title","message","date","seen"
        ]), (1,1))

def read_sheet_df(sh, title):
    try:
        ws = sh.worksheet_by_title(title)
        df = ws.get_as_df(empty_value="")
        # ensure index simple
        df.columns = df.columns.astype(str)
        return df.fillna("")
    except Exception as e:
        st.error(f"فشل قراءة الـSheet {title}: {e}")
        return pd.DataFrame()

def write_sheet_df(sh, title, df):
    ws = sh.worksheet_by_title(title)
    ws.set_dataframe(df, (1,1))

# ----------------- إرسال إيميل تنبيهي (اختياري) -----------------
def send_email(to_email, subject, body):
    if not EMAIL_USER or not EMAIL_PASS:
        st.warning("إرسال الإيميل غير مفعل. خزّن EMAIL_USER و EMAIL_PASS في .env إذا تريد التنبيهات عبر الإيميل.")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"فشل إرسال الإيميل: {e}")
        return False

# ------------------ واجهة التطبيق ------------------
st.set_page_config(page_title="تطبيق الموظفين - كامل", layout="wide")
st.markdown("""<style>
body {background: linear-gradient(180deg,#f7fbff,#e6f2ff);}
.card {padding:14px;border-radius:12px;background:white;box-shadow: 0 6px 18px rgba(2,6,23,0.06);margin-bottom:10px;}
h1 {color:#0b3b66;}
</style>""", unsafe_allow_html=True)

st.title("تطبيق الموظفين — كامل (مع Google Sheets)")
st.write("هنا الواجهة اللي تحفظ كلشي على Google Sheets: موظفين، طلبات، تحذيرات، إشعارات، شفتات")

# ---------- init GS ----------
sh = init_gsheets()
ensure_sheets_exist(sh)

# ---------- dataframes ----------
df_emp = read_sheet_df(sh, "Employees")
df_leaves = read_sheet_df(sh, "LeaveRequests")
df_warn = read_sheet_df(sh, "Warnings")
df_shifts = read_sheet_df(sh, "Shifts")
df_notifs = read_sheet_df(sh, "Notifications")

# ---------- Sidebar: login or admin ----------
st.sidebar.header("تسجيل دخول")
mode = st.sidebar.selectbox("أنا:", ["موظف", "أدمن"])

if mode == "موظف":
    emp_email_like = st.sidebar.text_input("اسم الموظف")
    emp_code_like = st.sidebar.text_input("الكود", type="password")
    btn_login = st.sidebar.button("دخول")
else:
    admin_user = st.sidebar.text_input("أدمن اسم", value="admin")
    admin_pass = st.sidebar.text_input("أدمن كود", type="password", value="admin123")
    btn_login = st.sidebar.button("دخول أدمن")

# ---------- LOGIN handling ----------
user = None
is_admin = False
if mode == "موظف" and btn_login:
    if df_emp.empty:
        st.error("قائمة الموظفين فارغة — أضف موظفين من لوحة الأدمن أولاً.")
    else:
        matched = df_emp[(df_emp["name"]==emp_email_like) & (df_emp["code"]==emp_code_like)]
        if matched.shape[0]==1:
            user = matched.iloc[0]
            st.success(f"مرحبا {user['name']}")
        else:
            st.error("اسم الموظف أو الكود غير صحيح.")
elif mode == "أدمن" and btn_login:
    # تأمين بسيط: لو admin/admin123 يدخل كأدمن
    if admin_user=="admin" and admin_pass=="admin123":
        is_admin = True
        st.success("تم دخول الأدمن")
    else:
        st.error("بيانات أدمن خاطئة (الافتراضي admin/admin123)")

# ---------- Admin Panel ----------
if is_admin:
    st.header("لوحة الأدمن 🔧")
    tab = st.tabs(["الموظفين","طلبات الإجازات","التحذيرات","الشفتات","الإشعارات"])
    # --- موظفين ---
    with tab[0]:
        st.subheader("قائمة الموظفين")
        st.dataframe(df_emp)
        st.markdown("---")
        st.subheader("إضافة موظف جديد")
        with st.form("add_emp"):
            ename = st.text_input("الاسم")
            ecode = st.text_input("الكود")
            epos = st.text_input("المنصب")
            ehome = st.text_input("السكن")
            start = st.date_input("تاريخ بدء العقد", value=date.today())
            end = st.date_input("تاريخ نهاية العقد", value=date.today().replace(year=date.today().year+1))
            submit_emp = st.form_submit_button("أضف الموظف")
        if submit_emp:
            new_id = 1
            if not df_emp.empty:
                new_id = int(df_emp["employee_id"].astype(int).max()) + 1
            new_row = {
                "employee_id": new_id, "name": ename, "code": ecode, "position": epos,
                "residence": ehome, "contract_start": start.strftime("%Y-%m-%d"),
                "contract_end": end.strftime("%Y-%m-%d"), "annual_leave":14,
                "sick_paid":0, "sick_unpaid":0,
                "sales_perf":0,"exams_perf":0,"commitment":0,"evaluation":0,"behavior":0,"total_perf":0,"points":0
            }
            df_emp = df_emp.append(new_row, ignore_index=True)
            write_sheet_df(sh,"Employees", df_emp)
            st.success(f"تم إضافة الموظف {ename}")
    # --- طلبات الإجازات ---
    with tab[1]:
        st.subheader("طلبات الإجازات")
        st.dataframe(df_leaves)
        st.markdown("*قبول/رفض الطلبات*")
        if not df_leaves.empty:
            sel = st.selectbox("اختر ID الطلب", df_leaves["id"].astype(str).tolist())
            if st.button("قبول"):
                df_leaves.loc[df_leaves["id"].astype(str)==sel, "status"] = "Approved"
                write_sheet_df(sh,"LeaveRequests", df_leaves)
                st.success("تم قبول الطلب")
            if st.button("رفض"):
                df_leaves.loc[df_leaves["id"].astype(str)==sel, "status"] = "Rejected"
                write_sheet_df(sh,"LeaveRequests", df_leaves)
                st.success("تم رفض الطلب")
    # --- التحذيرات ---
    with tab[2]:
        st.subheader("إضافة تحذير")
        with st.form("add_warning"):
            wid_emp = st.number_input("employee_id", min_value=1, step=1)
            wtype = st.selectbox("النوع", ["Temporary","First","Second","Third","Fourth"])
            wpoints = st.number_input("النقاط المضافة", min_value=1, step=1, value=20)
            wreason = st.text_input("السبب")
            submit_w = st.form_submit_button("أضف تحذير")
        if submit_w:
            new_id = 1
            if not df_warn.empty:
                new_id = int(df_warn["id"].astype(int).max()) + 1
            row = {"id":new_id,"employee_id":wid_emp,"name":"",
                   "type":wtype,"points":wpoints,"date":datetime.now().strftime("%Y-%m-%d"),
                   "reason":wreason,"deducted_salary":0,"status":"Active"}
            df_warn = df_warn.append(row, ignore_index=True)
            write_sheet_df(sh,"Warnings", df_warn)
            # update employee points if exists
            idx = df_emp.index[df_emp["employee_id"].astype(int)==wid_emp]
            if len(idx)>0:
                i = idx[0]
                df_emp.at[i,"points"] = int(df_emp.at[i,"points"]) + int(wpoints)
                write_sheet_df(sh,"Employees", df_emp)
            st.success("تم إضافة التحذير وتحديث النقاط (لو الموظف موجود).")
    # --- الشفتات ---
    with tab[3]:
        st.subheader("إضافة شفت")
        with st.form("add_shift"):
            sid_emp = st.number_input("employee_id", min_value=1, step=1)
            sdate = st.date_input("تاريخ الشفت", value=date.today())
            sshift = st.selectbox("نوع الشفت", ["Morning","Evening","Night"])
            sstart = st.text_input("Start (مثال 08:00)", "08:00")
            send = st.text_input("End (مثال 16:00)", "16:00")
            snote = st.text_input("ملاحظة")
            submit_s = st.form_submit_button("أضف شفت")
        if submit_s:
            new_id = 1
            if not df_shifts.empty:
                new_id = int(df_shifts["id"].astype(int).max()) + 1
            row = {"id":new_id,"employee_id":sid_emp,"date":sdate.strftime("%Y-%m-%d"),
                   "shift":sshift,"start":sstart,"end":send,"note":snote}
            df_shifts = df_shifts.append(row, ignore_index=True)
            write_sheet_df(sh,"Shifts", df_shifts)
            st.success("تم إضافة الشفت")
    # --- الاشعارات ---
    with tab[4]:
        st.subheader("إرسال إشعار لموظف")
        with st.form("send_notif"):
            nid_emp = st.number_input("employee_id", min_value=1, step=1)
            ntitle = st.text_input("عنوان")
            nmsg = st.text_area("الرسالة")
            send_now = st.form_submit_button("أرسل إشعار")
        if send_now:
            new_id = 1
            if not df_notifs.empty:
                new_id = int(df_notifs["id"].astype(int).max()) + 1
            row = {"id":new_id,"employee_id":nid_emp,"title":ntitle,"message":nmsg,"date":datetime.now().strftime("%Y-%m-%d %H:%M"),"seen":False}
            df_notifs = df_notifs.append(row, ignore_index=True)
            write_sheet_df(sh,"Notifications", df_notifs)
            st.success("تم إرسال الإشعار (محليًا في التطبيق).")
            # optional email
            # find employee email? we don't have email column; skip unless you add it
            if EMAIL_USER and ADMIN_EMAIL:
                send_email(ADMIN_EMAIL, f"Notification sent to {nid_emp}", f"{ntitle}\n\n{nmsg}")

# ---------- Employee view (بعد تسجيل الدخول) ----------
if user is not None:
    st.header("لوحة الموظف")
    st.markdown(f"{user['name']} — {user['position']}")
    # إشعارات
    my_notifs = df_notifs[df_notifs["employee_id"].astype(str)==str(int(user["employee_id"]))] if not df_notifs.empty else pd.DataFrame()
    st.subheader("🔔 الإشعارات")
    if my_notifs.empty:
        st.info("ماكو إشعارات جديدة")
    else:
        for i,row in my_notifs.iterrows():
            seen = str(row.get("seen","False")).lower() in ["true","1","yes"]
            if not seen:
                st.warning(f"{row['date']} — {row['title']}: {row['message']}")
            else:
                st.write(f"{row['date']} — {row['title']}: {row['message']}")
    # Dashboard cards
    st.subheader("🏠 الرئيسية")
    c1,c2,c3 = st.columns(3)
    with c1:
        st.markdown(f"<div class='card'><b>📊 الكواليتي</b><br>المجموع: <b>{user['total_perf']}</b>/100</div>", unsafe_allow_html=True)
        if st.button("عرض الكواليتي"):
            st.write({
                "sales": user["sales_perf"], "exams": user["exams_perf"], "commitment": user["commitment"],
                "evaluation": user["evaluation"], "behavior": user["behavior"], "total": user["total_perf"]
            })
    with c2:
        st.markdown(f"<div class='card'><b>🛌 الأوف السنوي</b><br>متبقي: <b>{user['annual_leave']}</b> يوم</div>", unsafe_allow_html=True)
        if st.button("طلب أوف"):
            fr = st.date_input("من تاريخ", value=date.today())
            to = st.date_input("إلى تاريخ", value=date.today())
            typ = st.selectbox("النوع", ["Annual","Sick(Paid)","Sick(Unpaid)"])
            if st.button("أرسل طلب الأوف"):
                new_id = 1
                if not df_leaves.empty:
                    try:
                        new_id = int(df_leaves["id"].astype(int).max()) + 1
                    except:
                        new_id = len(df_leaves)+1
                row = {"id":new_id,"employee_id":int(user["employee_id"]), "name":user["name"], "type":typ,
                       "from":fr.strftime("%Y-%m-%d"), "to":to.strftime("%Y-%m-%d"),
                       "proof_url":"", "status":"Pending", "submitted_at":datetime.now().strftime("%Y-%m-%d %H:%M")}
                df_leaves = df_leaves.append(row, ignore_index=True)
                write_sheet_df(sh,"LeaveRequests", df_leaves)
                st.success("تم إرسال طلب الإجازة بنجاح (حالة: Pending).")
                # أضف إشعار للأدمن
                new_nid = 1
                if not df_notifs.empty:
                    try:
                        new_nid = int(df_notifs["id"].astype(int).max()) + 1
                    except:
                        new_nid = len(df_notifs)+1
                nrow = {"id":new_nid,"employee_id":int(user["employee_id"]),"title":"طلب إجازة جديد",
                        "message":f"تم إرسال طلب إجازة من {user['name']}", "date":datetime.now().strftime("%Y-%m-%d %H:%M"), "seen":False}
                df_notifs = df_notifs.append(nrow, ignore_index=True)
                write_sheet_df(sh,"Notifications", df_notifs)
    with c3:
        st.markdown(f"<div class='card'><b>🤒 المرضي</b><br>مدفوع: <b>{user['sick_paid']}</b> | غير مدفوع: <b>{user['sick_unpaid']}</b></div>", unsafe_allow_html=True)
        if st.button("طلب مرضي"):
            prov = st.file_uploader("ارفق إثبات (اختياري)", type=["jpg","png","pdf"])
            if st.button("أرسل طلب المرضي"):
                new_id = 1
                if not df_leaves.empty:
                    try:
                        new_id = int(df_leaves["id"].astype(int).max()) + 1
                    except:
                        new_id = len(df_leaves)+1
                row = {"id":new_id,"employee_id":int(user["employee_id"]), "name":user["name"], "type":"Sick",
                       "from":date.today().strftime("%Y-%m-%d"), "to":date.today().strftime("%Y-%m-%d"),
                       "proof_url":"(uploaded)", "status":"Pending", "submitted_at":datetime.now().strftime("%Y-%m-%d %H:%M")}
                df_leaves = df_leaves.append(row, ignore_index=True)
                write_sheet_df(sh,"LeaveRequests", df_leaves)
                st.success("تم إرسال طلب المرضي (Pending).")
    # shifts
    st.subheader("📅 جدول الشفتات")
    my_shifts = df_shifts[df_shifts["employee_id"].astype(str)==str(int(user["employee_id"]))]
    if not my_shifts.empty:
        st.table(my_shifts.sort_values("date", ascending=False).head(10)[["date","shift","start","end","note"]])
    else:
        st.info("لا توجد شفتات مسجلة.")
    # warnings & points
    st.subheader("⚠ التحذيرات و النقاط")
    my_warns = df_warn[df_warn["employee_id"].astype(str)==str(int(user["employee_id"]))]
    if not my_warns.empty:
        st.table(my_warns[["date","type","points","reason","status"]])
    else:
        st.success("ماكو تحذيرات")
    st.info(f"النقاط الحالية: {user['points']} — تحذير كل 20 نقطة (المستوى: {int(user['points'])//20})")

# ---------- نهاية ----------
st.markdown("---")
st.caption ("تم تصميم التطبيق ليعمل مع Google Sheets. لو احتاجت أعدّل شيء أو أضيف ميزات (مثلاً إرسال WhatsApp أو Push Notifications) كلّه أقدر أطبّقه.")