// BackEnd/static/app.js

// --- 1. CONFIGURATION ---
const CATEGORIES_PREDEFINIES = [
    "Charges Fixes", "Alimentation", "Abonnements", "Sorties", 
    "Shopping", "Santé", "Transport", "Épargne", "Autres"
];

// --- 2. ÉLÉMENTS HTML ---
const loginView = document.getElementById('login-view');
const dashboardView = document.getElementById('dashboard-view');
const loginForm = document.getElementById('login-form');
const signupForm = document.getElementById('signup-form');
const showSignupBtn = document.getElementById('show-signup');
const showLoginBtn = document.getElementById('show-login');
const loginBtn = document.getElementById('login-btn');
const signupBtn = document.getElementById('signup-btn');
const logoutBtn = document.getElementById('logout-btn');
const loginEmail = document.getElementById('login-email');
const loginPassword = document.getElementById('login-password');
const signupEmail = document.getElementById('signup-email');
const signupPassword = document.getElementById('signup-password');
const authError = document.getElementById('auth-error');
const analyzeButton = document.getElementById('analyze-button');
const analyzeSection = document.getElementById('analyze-section');
const transactionsList = document.getElementById('transactions-list');
const analyzeBudgetButton = document.getElementById('analyze-budget-button');
const budgetButtonGroup = document.getElementById('budget-button-group');
const budgetCoachSection = document.getElementById('budget-coach');
const coachMessageText = document.getElementById('coach-message-text');
const enveloppesList = document.getElementById('enveloppes-list');
const dashboardPrincipal = document.getElementById('dashboard-principal');
const resteTotalText = document.getElementById('reste-total');
const resteJourText = document.getElementById('reste-jour');
const newTransactionForm = document.getElementById('new-transaction-form');
const newTxLibelle = document.getElementById('new-tx-libelle');
const newTxMontant = document.getElementById('new-tx-montant');
const goalSection = document.getElementById('goal-section');
const savingsGoalInput = document.getElementById('savings-goal');
const categoryModalBackdrop = document.getElementById('category-modal-backdrop');
const modalTxLibelle = document.getElementById('modal-tx-libelle');
const modalCategoryButtons = document.getElementById('modal-category-buttons');
const modalCancelBtn = document.getElementById('modal-cancel-btn');

// --- 3. MÉMOIRE LOCALE ---
let userToken = null; 
let transactionsNettoyees = [];
let currentBudget = {}; 
let txIdEnCoursDeCategorisation = null; 

// --- 4. FONCTIONS DE COMMUNICATION ---
async function fetchSecure(url, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };
    if (userToken) {
        headers['Authorization'] = `Bearer ${userToken}`;
    }
    const response = await fetch(url, { ...options, headers });
    if (response.status === 401) {
        handleLogout(); 
        return null;
    }
    if (!response.ok) {
         console.error(`Erreur ${response.status} de l'API ${url}:`, await response.text());
         return null;
    }
    const text = await response.text();
    return text ? JSON.parse(text) : {};
}

// 🆕 Charger les transactions depuis le serveur
async function loadTransactions() {
    const data = await fetchSecure('/api/transactions', { method: 'GET' });
    if (data) {
        transactionsNettoyees = data;
        displayTransactions(transactionsNettoyees);
    }
}

// 🆕 Ajouter une transaction sur le serveur
async function addTransaction(transaction) {
    const data = await fetchSecure('/api/transactions', {
        method: 'POST',
        body: JSON.stringify(transaction)
    });
    return data;
}

async function fetchCategorizedTransaction(transaction) {
    return await fetchSecure('/api/categorize', {
        method: 'POST',
        body: JSON.stringify(transaction)
    });
}

// --- 5. FONCTIONS D'AFFICHAGE ---
function displayTransactions(transactions) {
    transactionsList.innerHTML = ''; 
    const transactionsValides = transactions.filter(tx => tx);
    transactionsValides.sort((a, b) => new Date(a.date) - new Date(b.date));
    
    if (transactionsValides.length === 0) {
        transactionsList.innerHTML = '<li>Vous n\'avez encore aucune dépense. Utilisez le simulateur ci-dessous pour en ajouter !</li>';
        return;
    }
    
    for (const tx of transactionsValides) {
        const item = document.createElement('li');
        item.className = 'transaction-item';
        const amountClass = tx.montant > 0 ? 'positive' : 'negative';
        let categoryHtml = '';
        if (tx.categorie === 'A_VERIFIER') {
            categoryHtml = `<button class="categorize-btn" data-tx-id="${tx.id}">Catégoriser ?</button>`;
        } else {
            categoryHtml = `<div class="transaction-category">${tx.categorie || '...'} > ${tx.sous_categorie || '...'}</div>`;
        }
        item.innerHTML = `
            <div class="transaction-info">
                <div class="transaction-libelle">${tx.libelle_nettoye || tx.libelle}</div>
                <div class="transaction-details">${tx.date}</div>
                ${categoryHtml} 
             </div>
            <span class="transaction-amount ${amountClass}">${tx.montant.toFixed(2)} €</span>
        `;
        transactionsList.appendChild(item);
    }
}

function displayBudgetProposal(proposal) {
    resteTotalText.innerText = `${proposal.reste_a_vivre_total.toFixed(2)} €`;
    resteJourText.innerText = `soit ${proposal.reste_a_vivre_jour.toFixed(2)} € par jour`;
    dashboardPrincipal.style.display = 'block';
    coachMessageText.innerText = proposal.message_ia;
    enveloppesList.innerHTML = '';
    for (const env of proposal.enveloppes_proposees) {
        const item = document.createElement('div');
        item.className = 'enveloppe';
        item.innerHTML = `
            <span class="enveloppe-categorie">${env.categorie}</span>
            <span class="enveloppe-montant">
                <span id="env-restant-${env.categorie}">${env.montant_restant.toFixed(2)}</span> €
                / ${env.enveloppe_proposee} €
            </span>
        `;
        enveloppesList.appendChild(item);
    }
    budgetCoachSection.style.display = 'block';
    newTransactionForm.style.display = 'block'; 
}

function updateDashboardRealTime(newTransaction) {
    if (newTransaction && newTransaction.montant < 0) {
        const categorie = newTransaction.categorie;
        const montant = Math.abs(newTransaction.montant);
        
        const enveloppe = currentBudget.enveloppes_proposees.find(env => env.categorie === categorie);
        if (enveloppe) {
            enveloppe.montant_restant -= montant;
            const envElement = document.getElementById(`env-restant-${categorie}`);
            if (envElement) {
                envElement.innerText = enveloppe.montant_restant.toFixed(2);
            }
        }
        
        currentBudget.reste_a_vivre_total -= montant;
        currentBudget.reste_a_vivre_jour = currentBudget.reste_a_vivre_total / 30;
        
        resteTotalText.innerText = `${currentBudget.reste_a_vivre_total.toFixed(2)} €`;
        resteJourText.innerText = `soit ${currentBudget.reste_a_vivre_jour.toFixed(2)} € par jour`;
    }
}

// --- 6. LOGIQUE DES BOUTONS ET ACTIONS ---

// Logique d'authentification
showSignupBtn.addEventListener('click', (e) => {
    e.preventDefault();
    loginForm.style.display = 'none';
    signupForm.style.display = 'block';
    authError.style.display = 'none';
});

showLoginBtn.addEventListener('click', (e) => {
    e.preventDefault();
    loginForm.style.display = 'block';
    signupForm.style.display = 'none';
    authError.style.display = 'none';
});

signupBtn.addEventListener('click', async () => {
    const email = signupEmail.value;
    const password = signupPassword.value;
    if (!email || !password) {
        authError.innerText = "Email et mot de passe requis.";
        authError.style.display = 'block';
        return;
    }
    signupBtn.disabled = true;
    signupBtn.innerText = "Création...";
    authError.style.display = 'none';
    try {
        const response = await fetch('/api/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        if (response.status === 201) {
            authError.innerText = "Compte créé ! Vous pouvez vous connecter.";
            authError.style.display = 'block';
            showLoginBtn.click();
        } else {
            const error = await response.json();
            authError.innerText = error.msg || "Erreur.";
            authError.style.display = 'block';
        }
    } catch (e) {
        authError.innerText = "Erreur de connexion au serveur.";
        authError.style.display = 'block';
    } finally {
        signupBtn.disabled = false;
        signupBtn.innerText = "S'inscrire";
    }
});

loginBtn.addEventListener('click', async () => {
    const email = loginEmail.value;
    const password = loginPassword.value;
    if (!email || !password) {
        authError.innerText = "Email et mot de passe requis.";
        authError.style.display = 'block';
        return;
    }
    loginBtn.disabled = true;
    loginBtn.innerText = "Connexion...";
    authError.style.display = 'none';
    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        
        if (response.ok) {
            const data = await response.json();
            userToken = data.access_token;
            
            loginView.style.display = 'none';
            dashboardView.style.display = 'block';
            
            // 🆕 Charger les transactions de l'utilisateur
            await loadTransactions();
            
            // Afficher l'interface appropriée
            analyzeSection.style.display = 'none';
            goalSection.style.display = 'block';
            budgetButtonGroup.style.display = 'flex';
            newTransactionForm.style.display = 'block';
            
        } else {
            const error = await response.json();
            authError.innerText = error.msg || "Email ou mot de passe incorrect.";
            authError.style.display = 'block';
        }
    } catch (e) {
        authError.innerText = "Erreur de connexion au serveur.";
        authError.style.display = 'block';
    } finally {
        loginBtn.disabled = false;
        loginBtn.innerText = "Se Connecter";
    }
});
        
function handleLogout() {
    userToken = null;
    transactionsNettoyees = [];
    currentBudget = {};
    loginView.style.display = 'block';
    dashboardView.style.display = 'none';
    authError.innerText = "Vous avez été déconnecté.";
    authError.style.display = 'block';
    analyzeSection.style.display = 'block';
    goalSection.style.display = 'none';
    budgetButtonGroup.style.display = 'none';
    budgetCoachSection.style.display = 'none';
    dashboardPrincipal.style.display = 'none';
    newTransactionForm.style.display = 'none';
    transactionsList.innerHTML = '';
}

logoutBtn.addEventListener('click', handleLogout);

// Clic sur "Catégoriser ?" (Modale)
transactionsList.addEventListener('click', (event) => {
    if (event.target.classList.contains('categorize-btn')) {
        txIdEnCoursDeCategorisation = event.target.dataset.txId;
        const txNettoyee = transactionsNettoyees.find(tx => tx.id === txIdEnCoursDeCategorisation);
        modalTxLibelle.innerText = txNettoyee.libelle_nettoye;
        categoryModalBackdrop.classList.add('visible');
    }
});
        
// Clic sur un bouton de catégorie dans la modale
async function onCategorieSelectionnee(nouvelleCategorie) {
    if (!txIdEnCoursDeCategorisation) return; 
    
    const txNettoyee = transactionsNettoyees.find(tx => tx.id === txIdEnCoursDeCategorisation);
    
    // 🔧 CORRECTION : On utilise le libellé original de la transaction
    const motCle = txNettoyee.libelle.toUpperCase();
    
    // Mise à jour locale
    txNettoyee.categorie = nouvelleCategorie;
    txNettoyee.sous_categorie = "Validé par l'utilisateur";
    txNettoyee.methode = "Utilisateur";
    
    displayTransactions(transactionsNettoyees);
    
    if (currentBudget.reste_a_vivre_total !== undefined) {
         updateDashboardRealTime(txNettoyee);
    }
    
    // Apprentissage de la règle
    if (motCle) {
        try {
            await fetchSecure('/api/learn_rule', {
                method: 'POST',
                body: JSON.stringify({
                    'mot_cle': motCle,
                    'categorie': nouvelleCategorie
                })
            });
        } catch (error) {
            console.error("Erreur, impossible d'enseigner au Cerveau:", error);
        }
    }
    
    categoryModalBackdrop.classList.remove('visible');
    txIdEnCoursDeCategorisation = null;
}

// Connexion des boutons de la modale
modalCancelBtn.addEventListener('click', () => { 
    categoryModalBackdrop.classList.remove('visible');
    txIdEnCoursDeCategorisation = null;
});

modalCategoryButtons.addEventListener('click', (event) => { 
    if (event.target.classList.contains('category-button')) {
        onCategorieSelectionnee(event.target.dataset.category);
    }
});

function populerModalCategories() { 
    modalCategoryButtons.innerHTML = '';
    for (const cat of CATEGORIES_PREDEFINIES) {
        const btn = document.createElement('button');
        btn.className = 'category-button';
        btn.dataset.category = cat;
        btn.innerText = cat;
        modalCategoryButtons.appendChild(btn);
    }
}
        
// Bouton : Créer le budget
analyzeBudgetButton.addEventListener('click', async () => {
    const aVerifier = transactionsNettoyees.find(tx => tx.categorie === 'A_VERIFIER');
    if (aVerifier) { 
        alert("Veuillez d'abord catégoriser toutes les transactions !");
        return;
    }
    const objectifEpargne = parseFloat(savingsGoalInput.value) || 0;
    try {
        const payload = {
            transactions: transactionsNettoyees,
            objectif: objectifEpargne
        };
        const budgetProposal = await fetchSecure('/api/create_budget', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        
        if (budgetProposal) { 
            budgetProposal.enveloppes_proposees.forEach(env => {
                env.montant_restant = env.enveloppe_proposee;
            });
            currentBudget = budgetProposal; 
            displayBudgetProposal(currentBudget);
            analyzeBudgetButton.disabled = true;
            analyzeBudgetButton.innerText = "Budget Créé";
            goalSection.style.display = 'none';
        }
    } catch (error) { 
        console.error("Erreur de l'API Coach:", error);
    }
});
        
// Formulaire d'ajout de dépense
newTransactionForm.addEventListener('submit', async (event) => {
    event.preventDefault(); 
    const libelle = newTxLibelle.value;
    let montant = parseFloat(newTxMontant.value);
    
    if (!libelle || !montant) {
        alert("Veuillez remplir les deux champs.");
        return;
    }
    
    if (montant > 0) { 
        montant = -montant; 
    }
    
    // 🆕 Créer la nouvelle transaction
    const newTxBrute = {
        'date': new Date().toISOString().split('T')[0],
        'libelle': libelle.toUpperCase(),
        'montant': montant
    };
    
    // 🆕 L'envoyer au serveur pour qu'elle soit sauvegardée
    const newTxNettoyee = await addTransaction(newTxBrute);
    
    if (newTxNettoyee) {
        // Ajouter à notre liste locale
        transactionsNettoyees.push(newTxNettoyee);
        displayTransactions(transactionsNettoyees); 
        
        if (currentBudget.reste_a_vivre_total !== undefined) {
             updateDashboardRealTime(newTxNettoyee); 
        }
        
        if (newTxNettoyee.categorie === 'A_VERIFIER') {
            alert(`Nouvelle dépense ajoutée ! Veuillez la catégoriser dans la liste.`);
        }
    }
    
    newTxLibelle.value = '';
    newTxMontant.value = '';
});
        
// --- 7. INITIALISATION ---
populerModalCategories();