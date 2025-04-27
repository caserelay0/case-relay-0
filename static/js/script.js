// Main JavaScript for Case Study Generator

// Wait for DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Initialize components if they exist
    if (document.querySelector('#editor')) {
        initializeTinyMCE();
        setupImageSelection();
        setupAIAssistance();
    }
    
    // Set up file input label
    const fileInput = document.getElementById('document-upload');
    if (fileInput) {
        fileInput.addEventListener('change', function() {
            const fileName = this.files[0] ? this.files[0].name : 'Choose file...';
            const fileLabel = document.querySelector('.custom-file-label');
            fileLabel.textContent = fileName;
        });
    }
});

// Initialize TinyMCE editor
function initializeTinyMCE() {
    tinymce.init({
        selector: '#editor',
        height: 500,
        menubar: true,
        promotion: false, // Disable promotion
        branding: false, // Remove branding
        suffix: '.min',  // Use minified version
        // Use a minimal set of plugins to avoid loading errors
        plugins: 'lists link autolink',
        toolbar: 'undo redo | formatselect | ' +
        'bold italic | alignleft aligncenter ' +
        'alignright alignjustify | bullist numlist | ' +
        'removeformat',
        content_style: 'body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; font-size: 16px; }',
        // Silence warnings
        readonly: false,
        setup: function(editor) {
            editor.on('KeyUp', function(e) {
                // Save content when user stops typing
                clearTimeout(window.saveTimeout);
                window.saveTimeout = setTimeout(saveContent, 2000);
            });
            
            editor.on('NodeChange', function(e) {
                // Hide AI assist toolbar when selection changes
                const aiToolbar = document.getElementById('ai-assist-toolbar');
                if (aiToolbar) {
                    aiToolbar.style.display = 'none';
                }
            });
        }
    });
}

// Set up image selection functionality
function setupImageSelection() {
    const imageCards = document.querySelectorAll('.image-card');
    
    imageCards.forEach(function(card) {
        card.addEventListener('click', function() {
            // Toggle selection
            this.classList.toggle('selected');
            
            // Update hidden input with selected image IDs
            const selectedImages = Array.from(document.querySelectorAll('.image-card.selected'))
                .map(card => card.dataset.imageId);
            
            document.getElementById('selected-images').value = JSON.stringify(selectedImages);
        });
    });
}

// Set up AI assistance functionality
function setupAIAssistance() {
    document.addEventListener('mouseup', function() {
        const selection = window.getSelection();
        const selectedText = selection.toString().trim();
        
        if (selectedText.length > 10) {
            const range = selection.getRangeAt(0);
            const rect = range.getBoundingClientRect();
            
            showAIAssistToolbar(selectedText, rect);
        }
    });
}

// Show AI assistance toolbar
function showAIAssistToolbar(selectedText, rect) {
    let aiToolbar = document.getElementById('ai-assist-toolbar');
    
    // Create toolbar if it doesn't exist
    if (!aiToolbar) {
        aiToolbar = document.createElement('div');
        aiToolbar.id = 'ai-assist-toolbar';
        aiToolbar.className = 'ai-assist-toolbar';
        aiToolbar.innerHTML = `
            <button class="btn btn-sm btn-outline-primary" data-action="improve">Improve</button>
            <button class="btn btn-sm btn-outline-success" data-action="simplify">Simplify</button>
            <button class="btn btn-sm btn-outline-info" data-action="extend">Extend</button>
        `;
        document.body.appendChild(aiToolbar);
        
        // Add event listeners
        aiToolbar.addEventListener('click', function(e) {
            if (e.target.tagName === 'BUTTON') {
                const action = e.target.dataset.action;
                const selectedText = window.getSelection().toString().trim();
                
                if (selectedText) {
                    improveSelectedText(selectedText, action);
                }
                
                this.style.display = 'none';
            }
        });
    }
    
    // Position toolbar below the selection
    aiToolbar.style.left = rect.left + 'px';
    aiToolbar.style.top = (rect.bottom + window.scrollY + 10) + 'px';
    aiToolbar.style.display = 'block';
}

// Improve selected text using AI
function improveSelectedText(text, improvementType) {
    // Show loading indicator
    tinymce.activeEditor.setProgressState(true);
    
    // Send request to improve text
    fetch('/api/improve-text', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            text: text,
            type: improvementType
        }),
    })
    .then(response => response.json())
    .then(data => {
        if (data.improved_text) {
            // Replace selected text with improved text
            tinymce.activeEditor.selection.setContent(data.improved_text);
            showAlert('Text improved successfully!', 'success');
        } else {
            showAlert('Failed to improve text: ' + (data.error || 'Unknown error'), 'danger');
        }
    })
    .catch(error => {
        console.error('Error improving text:', error);
        showAlert('Error improving text. Please try again.', 'danger');
    })
    .finally(() => {
        tinymce.activeEditor.setProgressState(false);
    });
}

// Regenerate case study with different audience
function regenerateCaseStudy() {
    const audience = document.getElementById('audience-selector').value;
    
    // Show loading indicator
    document.getElementById('regenerate-btn').disabled = true;
    document.getElementById('regenerate-spinner').style.display = 'inline-block';
    
    // Send request to regenerate case study
    fetch('/api/regenerate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            audience: audience
        }),
    })
    .then(response => response.json())
    .then(data => {
        if (data.case_study) {
            // Update editor content
            tinymce.activeEditor.setContent(
                `<h1>${data.case_study.title}</h1>
                 <h2>Challenge</h2>
                 <p>${data.case_study.challenge}</p>
                 <h2>Approach</h2>
                 <p>${data.case_study.approach}</p>
                 <h2>Solution</h2>
                 <p>${data.case_study.solution}</p>
                 <h2>Outcomes</h2>
                 <p>${data.case_study.outcomes}</p>`
            );
            
            showAlert('Case study regenerated for audience: ' + audience, 'success');
        } else {
            showAlert('Failed to regenerate case study: ' + (data.error || 'Unknown error'), 'danger');
        }
    })
    .catch(error => {
        console.error('Error regenerating case study:', error);
        showAlert('Error regenerating case study. Please try again.', 'danger');
    })
    .finally(() => {
        document.getElementById('regenerate-btn').disabled = false;
        document.getElementById('regenerate-spinner').style.display = 'none';
    });
}

// Save content to server
function saveContent() {
    const content = tinymce.activeEditor.getContent();
    
    // Show loading indicator
    tinymce.activeEditor.setProgressState(true);
    
    // Send the content to the server
    fetch('/api/save-content', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            content: content
        }),
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert(data.message, 'success');
        } else {
            showAlert('Error saving content: ' + (data.error || 'Unknown error'), 'danger');
        }
    })
    .catch(error => {
        console.error('Error saving content:', error);
        showAlert('Error saving content. Please try again.', 'danger');
    })
    .finally(() => {
        tinymce.activeEditor.setProgressState(false);
    });
}

// Download case study as HTML
function downloadCaseStudy() {
    const content = tinymce.activeEditor.getContent();
    const title = document.querySelector('h1').innerText || 'Case Study';
    
    // Create HTML document
    const html = `
        <!DOCTYPE html>
        <html>
        <head>
            <title>${title}</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                h1 { color: #333; }
                h2 { color: #555; margin-top: 30px; }
                img { max-width: 100%; height: auto; }
            </style>
        </head>
        <body>
            ${content}
        </body>
        </html>
    `;
    
    // Create download link
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = title.replace(/[^a-z0-9]/gi, '_').toLowerCase() + '.html';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Show alert message
function showAlert(message, type) {
    const alertContainer = document.getElementById('alert-container');
    if (!alertContainer) return;
    
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.innerHTML = `
        ${message}
        <button type="button" class="close" data-dismiss="alert" aria-label="Close">
            <span aria-hidden="true">&times;</span>
        </button>
    `;
    
    alertContainer.appendChild(alert);
    
    // Auto dismiss after 5 seconds
    setTimeout(() => {
        alert.classList.remove('show');
        setTimeout(() => {
            alertContainer.removeChild(alert);
        }, 150);
    }, 5000);
}