#include "endstone_dynamic_properties/value.h"

#include <charconv>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace endstone_dynamic_properties {
namespace {
constexpr std::uint64_t FnvOffset = 1469598103934665603ULL;
constexpr std::uint64_t FnvPrime = 1099511628211ULL;

bool isContinuationByte(unsigned char value) noexcept {
    return value >= 0x80U && value <= 0xBFU;
}

bool isValidUtf8(std::string_view value) noexcept {
    std::size_t index = 0;
    while (index < value.size()) {
        const auto first = static_cast<unsigned char>(value[index]);
        if (first <= 0x7FU) {
            ++index;
            continue;
        }

        if (first >= 0xC2U && first <= 0xDFU) {
            if (value.size() - index < 2U ||
                !isContinuationByte(static_cast<unsigned char>(value[index + 1U]))) {
                return false;
            }
            index += 2U;
            continue;
        }

        if (first >= 0xE0U && first <= 0xEFU) {
            if (value.size() - index < 3U) return false;
            const auto second = static_cast<unsigned char>(value[index + 1U]);
            const auto third = static_cast<unsigned char>(value[index + 2U]);
            if (!isContinuationByte(third)) return false;
            if (first == 0xE0U) {
                if (second < 0xA0U || second > 0xBFU) return false;
            } else if (first == 0xEDU) {
                // UTF-16 surrogate code points are not Unicode scalar values.
                if (second < 0x80U || second > 0x9FU) return false;
            } else if (!isContinuationByte(second)) {
                return false;
            }
            index += 3U;
            continue;
        }

        if (first >= 0xF0U && first <= 0xF4U) {
            if (value.size() - index < 4U) return false;
            const auto second = static_cast<unsigned char>(value[index + 1U]);
            const auto third = static_cast<unsigned char>(value[index + 2U]);
            const auto fourth = static_cast<unsigned char>(value[index + 3U]);
            if (!isContinuationByte(third) || !isContinuationByte(fourth)) return false;
            if (first == 0xF0U) {
                if (second < 0x90U || second > 0xBFU) return false;
            } else if (first == 0xF4U) {
                if (second < 0x80U || second > 0x8FU) return false;
            } else if (!isContinuationByte(second)) {
                return false;
            }
            index += 4U;
            continue;
        }

        return false;
    }
    return true;
}

void appendUtf8(std::string &out, std::uint32_t code_point) {
    if (code_point <= 0x7FU) {
        out.push_back(static_cast<char>(code_point));
    } else if (code_point <= 0x7FFU) {
        out.push_back(static_cast<char>(0xC0U | (code_point >> 6U)));
        out.push_back(static_cast<char>(0x80U | (code_point & 0x3FU)));
    } else if (code_point <= 0xFFFFU) {
        out.push_back(static_cast<char>(0xE0U | (code_point >> 12U)));
        out.push_back(static_cast<char>(0x80U | ((code_point >> 6U) & 0x3FU)));
        out.push_back(static_cast<char>(0x80U | (code_point & 0x3FU)));
    } else {
        out.push_back(static_cast<char>(0xF0U | (code_point >> 18U)));
        out.push_back(static_cast<char>(0x80U | ((code_point >> 12U) & 0x3FU)));
        out.push_back(static_cast<char>(0x80U | ((code_point >> 6U) & 0x3FU)));
        out.push_back(static_cast<char>(0x80U | (code_point & 0x3FU)));
    }
}

void hashBytes(std::uint64_t &hash, std::string_view data) noexcept {
    for (const unsigned char c : data) {
        hash ^= c;
        hash *= FnvPrime;
    }
}

template <typename T>
void hashPod(std::uint64_t &hash, const T &value) noexcept {
    const auto *bytes = reinterpret_cast<const unsigned char *>(&value);
    for (std::size_t i = 0; i < sizeof(T); ++i) {
        hash ^= bytes[i];
        hash *= FnvPrime;
    }
}

std::string escapeJson(std::string_view value) {
    std::ostringstream out;
    for (const unsigned char c : value) {
        switch (c) {
        case '"': out << "\\\""; break;
        case '\\': out << "\\\\"; break;
        case '\b': out << "\\b"; break;
        case '\f': out << "\\f"; break;
        case '\n': out << "\\n"; break;
        case '\r': out << "\\r"; break;
        case '\t': out << "\\t"; break;
        default:
            if (c < 0x20) {
                out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                    << static_cast<int>(c) << std::dec;
            } else {
                out << static_cast<char>(c);
            }
        }
    }
    return out.str();
}

struct JsonValue {
    using Object = std::map<std::string, JsonValue>;
    using Array = std::vector<JsonValue>;
    std::variant<std::nullptr_t, bool, double, std::string, Object, Array> value{nullptr};
};

class JsonParser {
public:
    explicit JsonParser(std::string_view text) : text_(text) {}

    JsonValue parse() {
        skipSpace();
        auto value = parseValue();
        skipSpace();
        if (pos_ != text_.size()) fail("trailing data");
        return value;
    }

private:
    [[noreturn]] void fail(std::string_view message) const {
        throw std::runtime_error(std::string(message) + " at byte " + std::to_string(pos_));
    }

    void skipSpace() {
        while (pos_ < text_.size() && (text_[pos_] == ' ' || text_[pos_] == '\n' ||
               text_[pos_] == '\r' || text_[pos_] == '\t')) ++pos_;
    }

    char take() {
        if (pos_ >= text_.size()) fail("unexpected end of document");
        return text_[pos_++];
    }

    bool consume(std::string_view value) {
        if (text_.substr(pos_, value.size()) != value) return false;
        pos_ += value.size();
        return true;
    }

    JsonValue parseValue() {
        skipSpace();
        if (pos_ >= text_.size()) fail("expected value");
        const char c = text_[pos_];
        if (c == '{') return JsonValue{parseObject()};
        if (c == '[') return JsonValue{parseArray()};
        if (c == '"') return JsonValue{parseString()};
        if (c == 't' && consume("true")) return JsonValue{true};
        if (c == 'f' && consume("false")) return JsonValue{false};
        if (c == 'n' && consume("null")) return JsonValue{nullptr};
        if (c == '-' || (c >= '0' && c <= '9')) return JsonValue{parseNumber()};
        fail("invalid value");
    }

    JsonValue::Object parseObject() {
        JsonValue::Object object;
        if (take() != '{') fail("expected object");
        skipSpace();
        if (pos_ < text_.size() && text_[pos_] == '}') { ++pos_; return object; }
        for (;;) {
            skipSpace();
            if (pos_ >= text_.size() || text_[pos_] != '"') fail("expected object key");
            auto key = parseString();
            skipSpace();
            if (take() != ':') fail("expected colon");
            auto [it, inserted] = object.emplace(std::move(key), parseValue());
            if (!inserted) fail("duplicate object key");
            skipSpace();
            const char separator = take();
            if (separator == '}') break;
            if (separator != ',') fail("expected comma");
        }
        return object;
    }

    JsonValue::Array parseArray() {
        JsonValue::Array array;
        if (take() != '[') fail("expected array");
        skipSpace();
        if (pos_ < text_.size() && text_[pos_] == ']') { ++pos_; return array; }
        for (;;) {
            array.push_back(parseValue());
            skipSpace();
            const char separator = take();
            if (separator == ']') break;
            if (separator != ',') fail("expected comma");
        }
        return array;
    }

    static int hex(char c) {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return 10 + c - 'a';
        if (c >= 'A' && c <= 'F') return 10 + c - 'A';
        return -1;
    }

    std::uint32_t parseUnicodeCodeUnit() {
        std::uint32_t code = 0;
        for (int i = 0; i < 4; ++i) {
            if (pos_ >= text_.size()) fail("short unicode escape");
            const int digit = hex(take());
            if (digit < 0) fail("invalid unicode escape");
            code = (code << 4U) | static_cast<std::uint32_t>(digit);
        }
        return code;
    }

    std::string parseString() {
        if (take() != '"') fail("expected string");
        std::string out;
        while (pos_ < text_.size()) {
            const char c = take();
            if (c == '"') {
                if (!isValidUtf8(out)) fail("invalid UTF-8 in string");
                return out;
            }
            if (c != '\\') {
                if (static_cast<unsigned char>(c) < 0x20) fail("control character in string");
                out.push_back(c);
                continue;
            }
            const char escaped = take();
            switch (escaped) {
            case '"': out.push_back('"'); break;
            case '\\': out.push_back('\\'); break;
            case '/': out.push_back('/'); break;
            case 'b': out.push_back('\b'); break;
            case 'f': out.push_back('\f'); break;
            case 'n': out.push_back('\n'); break;
            case 'r': out.push_back('\r'); break;
            case 't': out.push_back('\t'); break;
            case 'u': {
                std::uint32_t code_point = parseUnicodeCodeUnit();
                if (code_point >= 0xD800U && code_point <= 0xDBFFU) {
                    if (!consume("\\u")) fail("high surrogate must be followed by low surrogate");
                    const std::uint32_t low = parseUnicodeCodeUnit();
                    if (low < 0xDC00U || low > 0xDFFFU) fail("invalid low surrogate");
                    code_point = 0x10000U + ((code_point - 0xD800U) << 10U) +
                                 (low - 0xDC00U);
                } else if (code_point >= 0xDC00U && code_point <= 0xDFFFU) {
                    fail("lone low surrogate");
                }
                appendUtf8(out, code_point);
                break;
            }
            default: fail("invalid string escape");
            }
        }
        fail("unterminated string");
    }

    double parseNumber() {
        const std::size_t start = pos_;
        if (text_[pos_] == '-') ++pos_;
        if (pos_ >= text_.size()) fail("invalid number");
        if (text_[pos_] == '0') ++pos_;
        else {
            if (text_[pos_] < '1' || text_[pos_] > '9') fail("invalid number");
            while (pos_ < text_.size() && text_[pos_] >= '0' && text_[pos_] <= '9') ++pos_;
        }
        if (pos_ < text_.size() && text_[pos_] == '.') {
            ++pos_;
            if (pos_ >= text_.size() || text_[pos_] < '0' || text_[pos_] > '9') fail("invalid fraction");
            while (pos_ < text_.size() && text_[pos_] >= '0' && text_[pos_] <= '9') ++pos_;
        }
        if (pos_ < text_.size() && (text_[pos_] == 'e' || text_[pos_] == 'E')) {
            ++pos_;
            if (pos_ < text_.size() && (text_[pos_] == '+' || text_[pos_] == '-')) ++pos_;
            if (pos_ >= text_.size() || text_[pos_] < '0' || text_[pos_] > '9') fail("invalid exponent");
            while (pos_ < text_.size() && text_[pos_] >= '0' && text_[pos_] <= '9') ++pos_;
        }
        const std::string number(text_.substr(start, pos_ - start));
        char *end = nullptr;
        const double value = std::strtod(number.c_str(), &end);
        if (!end || *end != '\0' || !std::isfinite(value)) fail("invalid finite number");
        return value;
    }

    std::string_view text_;
    std::size_t pos_{};
};

const JsonValue::Object *asObject(const JsonValue &value) {
    return std::get_if<JsonValue::Object>(&value.value);
}

const JsonValue::Array *asArray(const JsonValue &value) {
    return std::get_if<JsonValue::Array>(&value.value);
}

const std::string *asString(const JsonValue &value) {
    return std::get_if<std::string>(&value.value);
}

const double *asNumber(const JsonValue &value) {
    return std::get_if<double>(&value.value);
}

const bool *asBool(const JsonValue &value) {
    return std::get_if<bool>(&value.value);
}

const JsonValue *member(const JsonValue::Object &object, std::string_view key) {
    const auto it = object.find(std::string(key));
    return it == object.end() ? nullptr : &it->second;
}

} // namespace

std::string_view valueTypeName(const DynamicPropertyValue &value) noexcept {
    return std::visit([](const auto &entry) -> std::string_view {
        using T = std::decay_t<decltype(entry)>;
        if constexpr (std::is_same_v<T, bool>) {
            return "bool";
        } else if constexpr (std::is_same_v<T, double>) {
            return "number";
        } else if constexpr (std::is_same_v<T, std::string>) {
            return "string";
        } else {
            return "vector3";
        }
    }, value);
}

ValueValidationResult validateValue(const DynamicPropertyValue &value, const ValidationLimits &limits) {
    return std::visit([&](const auto &entry) -> ValueValidationResult {
        using T = std::decay_t<decltype(entry)>;
        if constexpr (std::is_same_v<T, double>) {
            if (!std::isfinite(entry)) return {false, "numbers must be finite"};
        } else if constexpr (std::is_same_v<T, std::string>) {
            if (entry.size() > limits.max_string_bytes) return {false, "string exceeds byte limit"};
            if (!isValidUtf8(entry)) return {false, "string must be valid UTF-8"};
        } else if constexpr (std::is_same_v<T, Vector3>) {
            if (!std::isfinite(entry.x) || !std::isfinite(entry.y) || !std::isfinite(entry.z))
                return {false, "vector coordinates must be finite"};
        }
        return {true, {}};
    }, value);
}

ValueValidationResult validateKey(std::string_view key, const ValidationLimits &limits) {
    if (key.empty()) return {false, "property key must not be empty"};
    if (key.size() > limits.max_key_bytes) return {false, "property key exceeds byte limit"};
    if (key.find('\0') != std::string_view::npos) return {false, "property key contains NUL"};
    if (!isValidUtf8(key)) return {false, "property key must be valid UTF-8"};
    return {true, {}};
}

ValueValidationResult validateCollectionName(std::string_view collection, const ValidationLimits &limits) {
    if (collection.empty()) return {false, "collection name must not be empty"};
    if (collection.size() > limits.max_collection_bytes) return {false, "collection name exceeds byte limit"};
    if (collection.find('\0') != std::string_view::npos) return {false, "collection name contains NUL"};
    if (!isValidUtf8(collection)) return {false, "collection name must be valid UTF-8"};
    return {true, {}};
}

std::uint64_t estimateStoredBytes(std::string_view key, const DynamicPropertyValue &value) noexcept {
    const std::uint64_t base = static_cast<std::uint64_t>(key.size()) + 8U;
    return base + std::visit([](const auto &entry) -> std::uint64_t {
        using T = std::decay_t<decltype(entry)>;
        if constexpr (std::is_same_v<T, bool>) {
            return 1U;
        } else if constexpr (std::is_same_v<T, double>) {
            return 8U;
        } else if constexpr (std::is_same_v<T, std::string>) {
            return static_cast<std::uint64_t>(entry.size());
        } else {
            return 24U;
        }
    }, value);
}

std::uint64_t hashValue(const DynamicPropertyValue &value) noexcept {
    std::uint64_t hash = FnvOffset;
    hashBytes(hash, valueTypeName(value));
    std::visit([&](const auto &entry) {
        using T = std::decay_t<decltype(entry)>;
        if constexpr (std::is_same_v<T, bool>) hashPod(hash, entry);
        else if constexpr (std::is_same_v<T, double>) hashPod(hash, entry);
        else if constexpr (std::is_same_v<T, std::string>) hashBytes(hash, entry);
        else {
            hashPod(hash, entry.x);
            hashPod(hash, entry.y);
            hashPod(hash, entry.z);
        }
    }, value);
    return hash;
}

std::string debugValue(const DynamicPropertyValue &value) {
    return std::visit([](const auto &entry) -> std::string {
        using T = std::decay_t<decltype(entry)>;
        if constexpr (std::is_same_v<T, bool>) {
            return entry ? "true" : "false";
        } else if constexpr (std::is_same_v<T, double>) {
            std::ostringstream out; out << std::setprecision(17) << entry; return out.str();
        } else if constexpr (std::is_same_v<T, std::string>) {
            return std::string("\"") + entry + "\"";
        } else {
            std::ostringstream out;
            out << "Vector3(" << std::setprecision(17) << entry.x << ',' << entry.y << ',' << entry.z << ')';
            return out.str();
        }
    }, value);
}

std::string encodeCollectionJson(
    const CollectionRef &ref,
    const DynamicPropertyMap &properties,
    std::uint64_t revision) {
    std::ostringstream out;
    out << "{\"schema\":1,\"target\":\"" << escapeJson(describeTarget(ref.target))
        << "\",\"collection\":\"" << escapeJson(ref.collection)
        << "\",\"revision\":" << revision << ",\"properties\":{";
    bool first = true;
    for (const auto &[key, value] : properties) {
        if (!first) out << ',';
        first = false;
        out << '\"' << escapeJson(key) << "\":{\"type\":\"" << valueTypeName(value) << "\",\"value\":";
        std::visit([&](const auto &entry) {
            using T = std::decay_t<decltype(entry)>;
            if constexpr (std::is_same_v<T, bool>) out << (entry ? "true" : "false");
            else if constexpr (std::is_same_v<T, double>) out << std::setprecision(17) << entry;
            else if constexpr (std::is_same_v<T, std::string>) out << '\"' << escapeJson(entry) << '\"';
            else out << '[' << std::setprecision(17) << entry.x << ',' << entry.y << ',' << entry.z << ']';
        }, value);
        out << '}';
    }
    out << "}}";
    return out.str();
}

std::optional<DynamicPropertyMap> decodeCollectionJson(std::string_view document, std::string *error) {
    try {
        const auto root = JsonParser(document).parse();
        const auto *root_object = asObject(root);
        if (!root_object) throw std::runtime_error("root must be an object");
        static const std::set<std::string> allowed_root_fields{
            "schema", "target", "collection", "revision", "properties"};
        for (const auto &member_entry : *root_object) {
            const auto &field = member_entry.first;
            if (!allowed_root_fields.contains(field))
                throw std::runtime_error("unknown root field: " + field);
        }
        const auto *schema_node = member(*root_object, "schema");
        const auto *schema = schema_node ? asNumber(*schema_node) : nullptr;
        if (!schema || *schema != 1.0) throw std::runtime_error("schema must be 1");
        const auto *properties_node = member(*root_object, "properties");
        const auto *properties = properties_node ? asObject(*properties_node) : nullptr;
        if (!properties) throw std::runtime_error("properties must be an object");
        DynamicPropertyMap result;
        for (const auto &[key, encoded] : *properties) {
            const auto *entry = asObject(encoded);
            if (!entry) throw std::runtime_error("property entry must be an object");
            if (entry->size() != 2 || !entry->contains("type") || !entry->contains("value"))
                throw std::runtime_error("property entry must contain only type and value");
            const auto *type_node = member(*entry, "type");
            const auto *value_node = member(*entry, "value");
            const auto *type = type_node ? asString(*type_node) : nullptr;
            if (!type || !value_node) throw std::runtime_error("property entry requires type and value");
            if (*type == "bool") {
                const auto *value = asBool(*value_node);
                if (!value) throw std::runtime_error("bool property has wrong value type");
                result.emplace(key, *value);
            } else if (*type == "number") {
                const auto *value = asNumber(*value_node);
                if (!value || !std::isfinite(*value)) throw std::runtime_error("number property has wrong value type");
                result.emplace(key, *value);
            } else if (*type == "string") {
                const auto *value = asString(*value_node);
                if (!value) throw std::runtime_error("string property has wrong value type");
                result.emplace(key, *value);
            } else if (*type == "vector3") {
                const auto *value = asArray(*value_node);
                if (!value || value->size() != 3) throw std::runtime_error("vector3 must have three coordinates");
                const auto *x = asNumber((*value)[0]);
                const auto *y = asNumber((*value)[1]);
                const auto *z = asNumber((*value)[2]);
                if (!x || !y || !z) throw std::runtime_error("vector3 coordinates must be numbers");
                result.emplace(key, Vector3{*x, *y, *z});
            } else {
                throw std::runtime_error("unknown property type: " + *type);
            }
        }
        return result;
    } catch (const std::exception &exception) {
        if (error) *error = exception.what();
        return std::nullopt;
    }
}

} // namespace endstone_dynamic_properties
