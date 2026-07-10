// static/js/main.js

// ===== TOGGLE MOBILE MENU =====
// Toggle class 'active' di wrapper navbar-menu, bukan di masing-masing element
function toggleMobileMenu() {
    const navbarMenu = document.getElementById('navbarMenu');
    const menuIcon = document.getElementById('menuIcon');
    
    if (navbarMenu && menuIcon) {
        navbarMenu.classList.toggle('active');
        
        // Ubah icon dari bars ke times (X)
        if (navbarMenu.classList.contains('active')) {
            menuIcon.classList.remove('fa-bars');
            menuIcon.classList.add('fa-times');
        } else {
            menuIcon.classList.remove('fa-times');
            menuIcon.classList.add('fa-bars');
        }
    }
}

// ===== AUTO-HIDE FLASH ALERTS =====
// Tunggu DOM selesai dimuat sebelum mencari elemen flash alert
document.addEventListener('DOMContentLoaded', function() {
    const flashAlerts = document.querySelectorAll('.flash-alert');
    
    flashAlerts.forEach(function(alert) {
        setTimeout(function() {
            alert.style.transition = 'opacity 0.5s ease';
            alert.style.opacity = '0';
            setTimeout(function() {
                alert.remove();
            }, 500);
        }, 5000); // Hilang setelah 5 detik
    });
});