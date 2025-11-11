// BackEnd/static/app.js

// --- 1. CONFIGURATION ---
const CATEGORIES_PREDEFINIES = [
    "Charges Fixes", "Alimentation", "Abonnements", "Sorties", 
    "Shopping", "Santé", "Transport", "Épargne", "Autres"
];

// --- CORRECTION : ON SUPPRIME LES DONNÉES BRUTES ---
// Un nouvel utilisateur commence à zéro.
// const transactions_brutes = [ ... ]; (SUPPRIMÉ)

// --- 2. ÉLÉMENTS HTML ---
const loginView = document.getElementById('login-view');
const dashboardView = document.getElementById('dashboard-view');
// ... (tous les autres const... C'est identique)
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
let transactionsNettoyees = []; // Commence vide !
let currentBudget = {}; 
let txIdEnCoursDeCategorisation = null; 

// --- 4. FONCTIONS DE COMMUNICATION ---
async function fetchSecure(url, options = {}) {
    // ... (fonction identique)
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

async function fetchCategorizedTransaction(transaction) {
    return await fetchSecure('/api/categorize', {
        method: 'POST',
        body: JSON.stringify(transaction)
    });
}

// --- 5. FONCTIONS D'AFFICHAGE ---
function displayTransactions(transactions) {
    // ... (fonction identique)
    transactionsList.innerHTML = ''; 
    const transactionsValides = transactions.filter(tx => tx);
    transactionsValides.sort((a, b) => new Date(a.date) - new Date(b.date));
    
    // --- CORRECTION : Message si la liste est vide ---
    if (transactionsValides.length === 0) {
        transactionsList.innerHTML = '<li>Vous n\'avez encore aucune dépense.</li>';
    }
    // --- FIN CORRECTION ---
    
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
            <span class="transaction-amount ${amountClass}">${tx.montant.toFixed(2)} €</span>
            <div class="transaction-libelle">${tx.libelle_nettoye || tx.libelle}</div>
            ${categoryHtml}
            <div class="transaction-details">${tx.date}</div>
        `;
        transactionsList.appendChild(item);
    }
}

function displayBudgetProposal(proposal) {
    // ... (fonction identique)
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
    // ... (fonction identique)
    if (newTransaction && newTransaction.montant < 0) {
        // ... (logique identique)
    }
}

// --- 6. LOGIQUE DES BOUTONS ET ACTIONS ---

// --- Logique d'authentification (Corrigée) ---
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
    // ... (fonction identique)
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
    // ... (fonction identique)
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
            
            // --- CORRECTION : On ne clique plus sur un bouton qui n'existe plus ---
            // analyzeButton.click(); (SUPPRIMÉ)
            
            // --- CORRECTION : On affiche directement le bon état ---
            analyzeSection.style.display = 'none'; // On cache le bouton d'analyse
            goalSection.style.display = 'block'; // On montre l'objectif
            budgetButtonGroup.style.display = 'flex'; // On montre le bouton "Créer Budget"
            newTransactionForm.style.display = 'block'; // On montre le simulateur
            displayTransactions([]); // On affiche la liste (vide)
            
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
    // ... (fonction identique)
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

// Bouton 1 : Analyser (Maintenant Inutilisé)
// analyzeButton.addEventListener('click', ... ); (SUPPRIMÉ)
        
// Clic sur "Catégoriser ?" (Modale)
transactionsList.addEventListener('click', (event) => {
    // ... (fonction identique)
    if (event.target.classList.contains('categorize-btn')) {
        txIdEnCoursDeCategorisation = event.target.dataset.txId;
        const txNettoyee = transactionsNettoyees.find(tx => tx.id === txIdEnCoursDeCategorisation);
        modalTxLibelle.innerText = txNettoyee.libelle_nettoye;
        categoryModalBackdrop.classList.add('visible');
    }
});
        
// Clic sur un bouton de catégorie dans la modale
async function onCategorieSelectionnee(nouvelleCategorie) {
    // ... (fonction identique)
    if (!txIdEnCoursDeCategorisation) return; 
    const txNettoyee = transactionsNettoyees.find(tx => tx.id === txIdEnCoursDeCategorisation);
    const txBrute = transactions_brutes.find(tx => tx.id === txIdEnCoursDeCategorISATION) || txNettoyee; // Oups, tx_brutes n'existe plus
    const txBruteCorrigee = transactionsNettoyees.find(tx => tx.id === txIdEnCoursDeCategorisation); // On utilise la liste nettoyée
    
    txNettoyee.categorie = nouvelleCategorie;
    txNettoyee.sous_categorie = "Validé par l'utilisateur";
    txNettoyee.methode = "Utilisateur";
    displayTransactions(transactionsNettoyees);
    if (currentBudget.reste_a_vivre_total !== undefined) {
         updateDashboardRealTime(txNettoyee);
    }
    
    const motCle = txBruteCorrigee.libelle.toUpperCase(); // On utilise le libellé brut (ou nettoyé, c'est ok)
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
modalCancelBtn.addEventListener('click', () => { /* ... (identique) ... */ });
modalCategoryButtons.addEventListener('click', (event) => { /* ... (identique) ... */ });
function populerModalCategories() { /* ... (identique) ... */ }
        
// Bouton 2 : Créer le budget
analyzeBudgetButton.addEventListener('click', async () => {
    // ... (fonction identique)
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
    // ... (fonction identique)
    event.preventDefault(); 
    const libelle = newTxLibelle.value;
    let montant = parseFloat(newTxMontant.value);
    if (!libelle || !montant) {
        alert("Veuillez remplir les deux champs.");
        return;
    }
    if (montant > 0) { montant = -montant; }
    
    // --- CORRECTION : On n'ajoute plus à "transactions_brutes" ---
    const newTxBrute = {
        'id': 'tx-' + Date.now(),
        'date': new Date().toISOString().split('T')[0],
        'libelle': libelle.toUpperCase(),
        'montant': montant
    };
    // transactions_brutes.push(newTxBrute); (SUPPRIMÉ)
    
    const newTxNettoyee = await fetchCategorizedTransaction(newTxBrute);
    if (newTxNettoyee) {
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
// On n'affiche plus rien au début.