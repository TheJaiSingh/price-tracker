-- Run this to (re)create the database with Google login + image support
CREATE DATABASE IF NOT EXISTS price_tracker;
USE price_tracker;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    google_id VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    product_url VARCHAR(1000) NOT NULL,
    product_name VARCHAR(255),
    image_url VARCHAR(1000),
    target_price DECIMAL(10, 2) NOT NULL,
    current_price DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS price_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

-- Agar tumhare paas pehle se products table hai (bina image_url ke),
-- to upar wali CREATE TABLE nahi chalegi (already exists). Us case mein
-- sirf ye ek line chala do:
-- ALTER TABLE products ADD COLUMN image_url VARCHAR(1000);
