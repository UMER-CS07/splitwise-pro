from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from Models.user import register_user, login_user
from Models.group import create_group, add_member_to_group, get_group_info
from Models.expense import add_expense, share_expense
from Models.feedback import add_feedback
from Models.settlement import add_settlement, update_settlement_status
from Models.connection import get_connection
from Models.group import get_group_summary
from flask import flash
import re  # We need this to check password patterns
from flask import flash, redirect, url_for
app = Flask(__name__)
app.secret_key = 'your_secret_key'

@app.route('/')
def home():
    # If the user is already logged in, you can optionally send them straight to the dashboard
    if 'user_id' in session:
        return redirect('/dashboard')
    
    # Otherwise, show the landing page
    return render_template('index.html')

# ------------------ Login ------------------
# ------------------ Login ------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.form
        email = data['email']
        password = data['password']

        # ✅ Basic Backend Validation before hitting the database
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash("❌ Invalid email format.", "error")
            return redirect('/login')

        if len(password) < 8:
            flash("❌ Password must be at least 8 characters.", "error")
            return redirect('/login')

        # Check credentials in the database
        user = login_user(email, password)
        if user:
            session['user_id'] = user['ID']
            flash("✅ Logged in successfully! Welcome, " + user['First_name'] + "!", "success")  
            return redirect('/dashboard')
        else:
            flash("❌ Invalid credentials. Please try again.", "error")
            return redirect('/login')
            
    return render_template('login.html')

# ------------------ Register ------------------
# ------------------ Register ------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.form
        password = data['password']
        email = data['email']

        # 1. Backend Email Validation
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash("❌ Invalid email format. Please use a valid email.", "error")
            return redirect('/register')

        # 2. Backend Password Validation
        if len(password) < 8 or not re.search("[a-z]", password) or not re.search("[A-Z]", password) or not re.search("[0-9]", password):
            flash("❌ Password must be at least 8 characters long and contain uppercase, lowercase, and a number.", "error")
            return redirect('/register')

        # 3. ✅ CHECK IF EMAIL ALREADY EXISTS
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ID FROM userr WHERE Email = %s", (email,))
        existing_user = cursor.fetchone()
        conn.close()

        if existing_user:
            flash("❌ This email is already registered! Please log in instead.", "error")
            return redirect('/register')

        # 4. If everything passes, register the user
        user_id = register_user(data['first_name'], data['last_name'], email, password)
        
        flash("✅ Account registered successfully! Please log in.", "success")  
        return redirect('/login')
    
    return render_template('register.html')
#-------------------------------------------------------

# ------------------ Dashboard ------------------
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    
    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Fetch User Data (Assuming your DB table is 'userr' based on your previous screenshot)
    cursor.execute("SELECT * FROM userr WHERE ID = %s", (user_id,))
    user_data = cursor.fetchone()

    # 2. Calculate TOTAL LENT (Using 'To_UserID' from your documentation)
    cursor.execute("""
        SELECT SUM(Amount) as total 
        FROM settlements 
        WHERE To_UserID = %s AND Status != 'complete'
    """, (user_id,))
    lent_res = cursor.fetchone()
    total_lent = lent_res['total'] if lent_res['total'] else 0

    # 3. Calculate TOTAL OWED (Using 'From_UserID' from your documentation)
    cursor.execute("""
        SELECT SUM(Amount) as total 
        FROM settlements 
        WHERE From_UserID = %s AND Status != 'complete'
    """, (user_id,))
    owed_res = cursor.fetchone()
    total_owed = owed_res['total'] if owed_res['total'] else 0

    # 4. Count Active Groups (Using 'group_members' or 'members' depending on your DB)
    cursor.execute("""
        SELECT COUNT(Group_ID) as count 
        FROM members 
        WHERE User_ID = %s
    """, (user_id,))
    group_res = cursor.fetchone()
    group_count = group_res['count'] if group_res['count'] else 0

    conn.close()
    
    return render_template('dashboard.html', 
                           user=user_data, 
                           total_lent="{:,.2f}".format(total_lent), 
                           total_owed="{:,.2f}".format(total_owed), 
                           group_count=group_count)
#====================================================
#====================================================
@app.route('/settle-wallet/single/<int:settlement_id>', methods=['POST'])
def settle_single_wallet(settlement_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Step 1: Get user's wallet balance
        cursor.execute("SELECT Wallet FROM userr WHERE ID = %s", (user_id,))
        user_data = cursor.fetchone()
        wallet = float(user_data['Wallet']) if user_data and user_data['Wallet'] is not None else 0.0

        # Step 2: Get the specific settlement details
        cursor.execute("""
            SELECT s.ID, s.To_UserID, s.Amount, s.Group_ID, g.Group_name 
            FROM settlements s
            JOIN Groups g ON s.Group_ID = g.ID
            WHERE s.ID = %s AND s.From_UserID = %s AND s.Status = 'pending'
        """, (settlement_id, user_id))
        settlement = cursor.fetchone()

        if not settlement:
            flash("❌ Settlement not found or already paid.", "error")
            return redirect('/groups')

        group_id = settlement['Group_ID']
        group_name = settlement['Group_name']
        amount = float(settlement['Amount'])
        to_user = settlement['To_UserID']

        # Step 3: Check if they have enough money
        if wallet < amount:
            flash(f"❌ Not enough Wallet balance! You need ${amount} but only have ${wallet}.", "error")
            return redirect(f'/group/{group_id}/summary')

        # Step 4: Process the payment
        cursor.execute("UPDATE userr SET Wallet = Wallet - %s WHERE ID = %s", (amount, user_id))
        cursor.execute("UPDATE userr SET Wallet = Wallet + %s WHERE ID = %s", (amount, to_user))
        cursor.execute("UPDATE settlements SET Status = 'complete', Settlement_Date = NOW() WHERE ID = %s", (settlement_id,))

        conn.commit()
        
        # ✅ SUCCESS: Render the receipt for this specific payment!
        return render_template("receipt.html", amount=amount, group_name=group_name, group_id=group_id)

    except Exception as e:
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
        flash(f"❌ Error processing payment: {str(e)}", "error")
        return redirect('/groups')
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()
# ------------------ Logout ------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')
##################################################
@app.route('/group/<int:group_id>/summary')
def group_summary(group_id):
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Get group info
    cursor.execute("SELECT * FROM groups WHERE ID = %s", (group_id,))
    group = cursor.fetchone()

    # Get members
    cursor.execute("""
        SELECT u.ID, u.First_name, u.Last_name 
        FROM members gm 
        JOIN userr u ON gm.User_ID = u.ID 
        WHERE gm.Group_ID = %s
    """, (group_id,))
    members = cursor.fetchall()
    member_ids = [str(member['ID']) for member in members]

    # Get expenses
    cursor.execute("""
        SELECT e.ID, e.Description, e.Amount, u.First_name AS Paid_by
        FROM expenses e
        JOIN userr u ON e.Pair_ID = u.ID
        WHERE e.Group_ID = %s
    """, (group_id,))
    expenses = cursor.fetchall()

    # Get settlements related to these members
    if member_ids:
        ids_str = ",".join(member_ids)
        cursor.execute("""
    SELECT s.*, 
           uf.First_name AS From_Name, 
           ut.First_name AS To_Name
    FROM settlements s
    JOIN userr uf ON s.From_UserID = uf.ID
    JOIN userr ut ON s.To_UserID = ut.ID
    WHERE s.Group_ID = %s
""", (group_id,))
        settlements = cursor.fetchall()
    else:
        settlements = []

    conn.close()

    return render_template('group_summary.html',
                           group=group,
                           members=members,
                           expenses=expenses,
                           settlements=settlements)

##################################################
##################################################
@app.route('/add-expense/<int:group_id>', methods=['GET', 'POST'])
def handle_add_expense(group_id):
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Fetch group info and creator
        cursor.execute("SELECT Group_name, Created_by FROM Groups WHERE ID = %s", (group_id,))
        group = cursor.fetchone()

        if not group:
            conn.close()
            flash("❌ Group not found.", "error")
            return redirect('/groups')

        # ❌ If not the creator, deny access
        if int(group['Created_by']) != int(user_id):
            conn.close()
            flash("❌ Only the group creator can add expenses.", "error")
            return redirect(f'/group/{group_id}/summary')

        if request.method == 'GET':
            # Load members to show in form
            cursor.execute("""
                SELECT u.ID, u.First_name
                FROM members m
                JOIN userr u ON u.ID = m.User_ID
                WHERE m.Group_ID = %s
            """, (group_id,))
            members = cursor.fetchall()
            conn.close()
            return render_template("add_expense.html", group=group, members=members, group_id=group_id)

        elif request.method == 'POST':
            desc = request.form['description']
            amount = float(request.form['amount'])
            pair_id = int(request.form['pair_id'])
            
            # Use getlist to get multiple selected checkboxes
            involved_users = request.form.getlist('involved_users')

            # ✅ SAFETY CHECK: Prevent Divide by Zero
            if not involved_users or len(involved_users) == 0:
                flash("❌ You must select at least one member to share the expense with!", "error")
                conn.close()
                return redirect(f'/add-expense/{group_id}')

            expense_id = add_expense(group_id, pair_id, amount, desc)
            share_amount = round(amount / len(involved_users), 2)

            for uid in involved_users:
                uid = int(uid)
                share_expense(expense_id, uid, share_amount)

                if uid != pair_id:
                    add_settlement(
                        from_user_id=uid,
                        to_user_id=pair_id,
                        amount=share_amount,
                        status='pending',
                        group_id=group_id
                    )

            conn.close()
            flash("✅ Expense added successfully!", "success")
            return redirect(f'/group/{group_id}/summary')

    except Exception as e:
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
            conn.close()
        flash(f"❌ Error: {str(e)}", "error")
        return redirect(f'/group/{group_id}/summary')


#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

# ------------------ View Groups ------------------
@app.route('/groups')
def groups():
    if 'user_id' not in session:
        return redirect('/login')

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT distinct  g.* FROM Groups g
        JOIN Members m ON g.ID = m.Group_ID
        WHERE m.User_ID = %s
    """, (session['user_id'],))
    group_list = cursor.fetchall()
    conn.close()
    
    return render_template('groups.html', group_list=group_list)

# ------------------ Create Group Page ------------------
@app.route('/create-group')
def create_group_page():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template("create_group.html", user_id=session['user_id'])
#################################
@app.route('/group/<int:group_id>')
def view_group(group_id):
    if 'user_id' not in session:
        return redirect('/login')
    try:
        group_data = get_group_info(group_id)
        group = get_group_info(group_id) 
        return render_template('group_details.html', group=group_data)
    except Exception as e:
        return render_template('error.html', error_message=str(e))

# ------------------ API: Create Group ------------------
@app.route('/api/create-group', methods=['POST'])
def group():
    try:
        group_name = request.form['group_name']
        created_by = request.form['created_by']
        passcode = request.form['group_passcode'] # ✅ Capture the passcode

        # Pass it to your model function
        group_id = create_group(group_name, created_by, passcode) 
        
        flash(f"✅ Group '{group_name}' created successfully! Share the passcode with your friends.", "success")
        return redirect('/groups')
    except Exception as e:
        return render_template('error.html', error_message=str(e))

# ------------------ Join Group Page ------------------
@app.route('/join-group', methods=['GET', 'POST'])
def join_group():
    if 'user_id' not in session:
        return redirect('/login')

    if request.method == 'POST':
        try:
            group_id = request.form['group_id']
            passcode_attempt = request.form['group_passcode'] # ✅ Capture the passcode attempt

            conn = get_connection()
            cursor = conn.cursor(dictionary=True) # ✅ Using dictionary to easily check the Passcode column

            # 1. Check if group exists AND get its real passcode
            cursor.execute("SELECT ID, Passcode FROM Groups WHERE ID = %s", (group_id,))
            group = cursor.fetchone()

            if not group:
                raise Exception("Group not found. Please check the Group ID.")

            # 2. ✅ Verify the Passcode
            if group['Passcode'] != passcode_attempt:
                raise Exception("Incorrect Group Passcode! Access Denied.")

            # 3. Check if user is already a member
            cursor.execute("SELECT * FROM Members WHERE Group_ID = %s AND User_ID = %s", (group_id, session['user_id']))
            if cursor.fetchone():
                raise Exception("Already a member of this group")

            # 4. Add member
            cursor.execute("INSERT INTO Members (Group_ID, User_ID, Joined_at) VALUES (%s, %s, NOW())", (group_id, session['user_id']))
            conn.commit()
            conn.close()

            flash("✅ Successfully joined the group!", "success")
            return redirect('/groups') # Redirect to groups instead of staying on the join page
            
        except Exception as e:
            return render_template('join_group.html', message="❌ " + str(e))

    return render_template('join_group.html')

# ------------------ API: Add Member to Group ------------------
@app.route('/group/member', methods=['POST'])
def add_member():
    try:
        data = request.get_json(force=True)
        group_id = data['group_id']
        user_id = data['user_id']

        conn = get_connection()
        cursor = conn.cursor()

        # Check for duplicate
        cursor.execute("SELECT 1 FROM Members WHERE Group_ID = %s AND User_ID = %s", (group_id, user_id))
        if cursor.fetchone():
            return jsonify({"status": "error", "message": "User already a member of this group"}), 400

        # Add if not exists
        cursor.execute("INSERT INTO Members (Group_ID, User_ID, Joined_at) VALUES (%s, %s, NOW())", (group_id, user_id))
        conn.commit()
        conn.close()

        return jsonify({"message": "Member added to group", "status": "success"})
    except Exception as e:
        return jsonify({"message": str(e), "status": "error"}), 500


# ------------------ API: Add Expense ------------------
@app.route('/expense', methods=['POST'])
def expense():
    data = request.json
    try:
        expense_id = add_expense(data['group_id'], data['pair_id'], data['amount'], data['description'])
        return jsonify({"status": "success", "expense_id": expense_id})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ------------------ API: Share Expense ------------------
@app.route('/expense/share', methods=['POST'])
def share():
    data = request.json
    try:
        share_expense(data['expense_id'], data['user_id'], data['share_amount'])
        return jsonify({"status": "shared successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ------------------ API: Submit Feedback ------------------


# ------------------ API: Add Settlement ------------------
@app.route('/settle', methods=['POST'])
def settle():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "❌ Unauthorized"}), 401

    data = request.json
    try:
        from_user = session['user_id']  # secure: use session, not frontend
        to_user = data['to_user_id']
        amount = data['amount']
        group_id = data.get('group_id')

        if not group_id:
            return jsonify({"status": "error", "message": "❌ Missing group ID"}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # ✅ Check if requester is the group creator
        cursor.execute("SELECT Created_by FROM Groups WHERE ID = %s", (group_id,))
        group = cursor.fetchone()

        if not group:
            return jsonify({"status": "error", "message": "❌ Group not found"}), 404

        if int(group['Created_by']) != int(from_user):
            return jsonify({
                "status": "error",
                "message": "❌ Permission denied. Only the group creator can add settlements."
            }), 403

        # ✅ Add the settlement
        settlement_id = add_settlement(
            from_user_id=from_user,
            to_user_id=to_user,
            amount=amount,
            status=data.get('status', 'pending'),
            group_id=group_id
        )

        conn.close()
        return jsonify({"status": "settlement recorded", "settlement_id": settlement_id})

    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return jsonify({"status": "error", "message": str(e)}), 500



# ------------------ API: Update Settlement Status ------------------
@app.route('/settle/<int:settlement_id>', methods=['PUT'])
def update_settle(settlement_id):
    data = request.json
    try:
        update_settlement_status(settlement_id, data['status'])
        return jsonify({"status": "settlement updated"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ------------------ API: Delete Settlement ------------------
@app.route('/settlement/delete/<int:settlement_id>', methods=['POST'])
def delete_settlement(settlement_id):
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Step 1: Check if settlement exists AND find out who created the group
        cursor.execute("""
            SELECT s.ID, s.Group_ID, g.Created_by 
            FROM settlements s
            JOIN Groups g ON s.Group_ID = g.ID
            WHERE s.ID = %s
        """, (settlement_id,))
        settlement = cursor.fetchone()

        # Error: Settlement doesn't exist
        if not settlement:
            flash("❌ Settlement not found.", "error")
            return redirect('/groups') # Redirect to all groups if we don't know the specific group ID

        group_id = settlement['Group_ID']

        # Step 2: SECURITY CHECK - Only the Group Admin can delete it
        if settlement['Created_by'] != user_id:
            flash("❌ Unauthorized: Only the Group Admin can delete settlements.", "error")
            return redirect(f'/group/{group_id}/summary')

        # Step 3: Delete settlement
        cursor.execute("DELETE FROM settlements WHERE ID = %s", (settlement_id,))
        conn.commit()

        # ✅ SUCCESS: Flash the green notification and stay on the summary page!
        flash("✅ Settlement deleted successfully.", "success")
        return redirect(f'/group/{group_id}/summary')
    
    except Exception as e:
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
        flash(f"❌ Error deleting settlement: {str(e)}", "error")
        return redirect('/groups')
    
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()
#---------------------------------------------------------------------------------
# ------------------ API: Delete Group ------------------
@app.route('/delete-group/<int:group_id>', methods=['POST'])
def delete_group(group_id):
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Step 1: Check if group exists and if the logged-in user is the Admin
        cursor.execute("SELECT Created_by FROM Groups WHERE ID = %s", (group_id,))
        group = cursor.fetchone()

        if not group:
            flash("❌ Group not found.", "error")
            return redirect('/groups')

        if int(group['Created_by']) != int(user_id):
            flash("❌ Unauthorized: Only the Group Admin can delete this group.", "error")
            return redirect('/groups')
# Step 2: Delete "grandchildren" first (expense_share depends on expenses)
        cursor.execute("""
            DELETE FROM expense_share 
            WHERE Expense_ID IN (SELECT ID FROM expenses WHERE Group_ID = %s)
        """, (group_id,))

        # Step 3: Delete "children" (these depend directly on the Group)
        cursor.execute("DELETE FROM settlements WHERE Group_ID = %s", (group_id,))
        cursor.execute("DELETE FROM expenses WHERE Group_ID = %s", (group_id,))
        
        # 👇 REMOVED the group_members line since your table is named differently!
        # cursor.execute("DELETE FROM group_members WHERE Group_ID = %s", (group_id,))

        # Step 4: Now it is safe to delete the parent (the Group itself)
        cursor.execute("DELETE FROM Groups WHERE ID = %s", (group_id,))
        
        # Save all the deletions!
        conn.commit()
        
        flash("✅ Group successfully deleted.", "success")
        
    except Exception as e:
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
        flash(f"❌ Error deleting group: {str(e)}", "error")
        
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()

    return redirect('/groups')
#---------------------------------------------------------------------------------
#------------------------------------------------------------------
# ------------------ Combined Feedback & Reviews ------------------
@app.route('/feedback', methods=['GET', 'POST'])
def feed_back():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # 1. Handle New Feedback Submission
    if request.method == 'POST':
        try:
            # Check if already submitted
            cursor.execute("SELECT * FROM feedback WHERE From_UserID = %s", (user_id,))
            existing = cursor.fetchone()
            
            if not existing:
                description = request.form['description']
                rating = int(request.form['rating'])

                cursor.execute("""
                    INSERT INTO feedback (From_UserID, Description, Rating, Created_At)
                    VALUES (%s, %s, %s, NOW())
                """, (user_id, description, rating))
                conn.commit()
                flash("✅ Feedback submitted successfully!", "success")
        except Exception as e:
            conn.rollback()
            conn.close()
            return render_template("error.html", error_message="❌ " + str(e))

    # 2. Fetch the current user's feedback (if any)
    cursor.execute("SELECT * FROM feedback WHERE From_UserID = %s", (user_id,))
    user_feedback = cursor.fetchone()

    # 3. Fetch ALL community feedback
    cursor.execute("""
        SELECT f.Description, f.Rating, f.Created_At, u.First_name, u.Last_name 
        FROM feedback f
        JOIN userr u ON f.From_UserID = u.ID
        ORDER BY f.Created_At DESC
    """)
    all_reviews = cursor.fetchall()

    conn.close()
    
    # 4. Send BOTH to the single feedback.html template
    return render_template("feedback.html", user_feedback=user_feedback, all_reviews=all_reviews)


# =====================================================

if __name__ == '__main__':
    print("Successfully done")
    app.run(debug=True)


