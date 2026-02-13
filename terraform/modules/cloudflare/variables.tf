variable "zone_id" {
  description = "Cloudflare Zone ID"
  type        = string
}

variable "domain" {
  description = "Root domain managed in Cloudflare"
  type        = string
}

variable "app_origin" {
  description = "Target for app subdomain (LB IP/hostname)"
  type        = string
  default     = ""
}

variable "api_origin" {
  description = "Target for api subdomain (LB IP/hostname)"
  type        = string
  default     = ""
}

variable "staging_origin" {
  description = "Target for staging subdomain (LB IP/hostname). Leave empty to skip."
  type        = string
  default     = ""
}

variable "app_record_type" {
  description = "DNS record type for app target (A/CNAME)"
  type        = string
  default     = "A"
}

variable "api_record_type" {
  description = "DNS record type for api target (A/CNAME)"
  type        = string
  default     = "A"
}

variable "staging_record_type" {
  description = "DNS record type for staging target (A/CNAME)"
  type        = string
  default     = "A"
}

variable "app_proxied" {
  description = "Whether app hostname is proxied through Cloudflare"
  type        = bool
  default     = true
}

variable "api_proxied" {
  description = "Whether api hostname is proxied through Cloudflare"
  type        = bool
  default     = false
}

variable "staging_proxied" {
  description = "Whether staging hostname is proxied through Cloudflare"
  type        = bool
  default     = false
}

variable "ssl_mode" {
  description = "Cloudflare SSL mode for the zone (off/flexible/full/strict)"
  type        = string
  default     = "strict"
}

variable "always_use_https" {
  description = "Enable Always Use HTTPS setting in Cloudflare"
  type        = bool
  default     = true
}

variable "enable_zone_settings" {
  description = "Manage Cloudflare zone settings override"
  type        = bool
  default     = false
}
